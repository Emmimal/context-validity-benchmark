# context-validity-benchmark

A deterministic, zero-dependency benchmark measuring what it actually costs when an AI agent keeps acting on context that was true once and isn't anymore.

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Dependencies](https://img.shields.io/badge/core%20dependencies-none-brightgreen)

Most agent frameworks track what's *present* in context. Almost none track whether it's still *valid*. This repo isolates that one mechanism: two identical executors, differing only in whether they check a dependency's validity before acting on it, or only discover it's broken when an action fails. No LLM, no API, no embeddings, nothing that would confound the measurement.

Read the full write-up on Towards Data Science → **[Context Windows Don’t Know What’s Still True — I Built a System That Does](https://towardsdatascience.com/author/emmimalp.alexander/)**


---

## What It Does

```
Scenario (facts + dependency graph + scheduled events + step budget)
                        │
                        ▼
              TaskWorld (live facts, ground truth, event schedule)
                        │
            ┌───────────┴────────────┐
            ▼                        ▼
     Baseline Executor      Validity-Aware Executor
   (detects at execution      (checks dependency
      time, late but            status first,
       not blind)                early detection)
            │                        │
            └───────────┬────────────┘
                        ▼
        TaskResult (steps_used, PFW, SCUR, replans,
                verifications, completed)
```

Five modules, no orchestration framework needed:

| Module | Job |
|---|---|
| `facts.py` | `Fact` and `ValidityState` (ACTIVE / STALE / SUPERSEDED / UNKNOWN) — the belief layer each executor actually sees |
| `graph.py` | `DependencyGraph`, `Step`, and three topology generators: `generate_chain`, `generate_branching`, `generate_multi_branch` |
| `world.py` | `TaskWorld` — live facts, scheduled `InvalidationEvent`s, and the ground-truth/belief split neither executor is allowed to cheat on |
| `executors.py` | `run_baseline`, `run_validity_aware`, `TaskResult`, and the step-budget formula |
| `scenarios.py` | The 7 named scenarios (C, A, D1, D2, D3, E1, E2) plus the 96-config parameter grid and the budget sweep |

---

## Installation

```bash
git clone https://github.com/Emmimal/context-validity-benchmark.git
cd context-validity-benchmark
```

No `pip install` required for the benchmark itself. Everything under `context_validity/` runs on the Python standard library only, fully deterministic, no API keys, no network calls.

```bash
pip install matplotlib   # optional — only needed for make_figures.py
```

`matplotlib` is the one dependency exception in the whole project, used solely to render the article's charts from already-computed results. It's never imported by the benchmark logic itself.

---

## Quick Start

```python
from context_validity.scenarios import scenario_A_value_change

baseline, validity_aware = scenario_A_value_change(depth=4, change_tick=1)

print(f"Baseline:       {baseline.steps_used} steps, {baseline.pre_failure_work} doomed actions")
print(f"Validity-aware: {validity_aware.steps_used} steps, {validity_aware.pre_failure_work} doomed actions")

# Baseline:       9 steps, 2 doomed actions
# Validity-aware: 6 steps, 0 doomed actions
```

Both executors get the identical task, the identical sequence of world changes, and the identical recovery cost once they decide to replan. The only thing that differs is *when* each one finds out something broke.

---

## Running the Full Benchmark

| Script | What it does |
|---|---|
| `run_all.py` | Runs all 7 scenarios plus the robustness checks, prints result tables, writes `results.json` |
| `verify_pfw_law.py` | Analytically derives expected Pre-Failure Work from graph structure alone (no executor run) and checks it against actual output across 15 cases spanning every topology and fault-timing variant |
| `make_figures.py` | Renders the 4 article figures from `results.json` (requires matplotlib) |
| `make_charts.py` | Renders ASCII bar charts from `results.json`, zero dependencies |

```bash
python run_all.py
python verify_pfw_law.py
python make_figures.py     # optional, needs matplotlib
```

---

## The Closed-Form Law

Every Pre-Failure Work number this benchmark produces, across every topology and every fault-injection timing, obeys one exact rule:

```
baseline_pfw = (non-action steps in the invalidated fact's dependency
                closure that haven't executed yet when the fault happens)
```

For any scenario where the fault happens before the plan starts, this collapses to `closure_size - 1`. Verified against 15 cases with zero exceptions by `verify_pfw_law.py`, which derives the expected value from graph structure directly, without ever calling either executor.

This came out of a real correction, not a planned result: an early version of this benchmark hand-picked 3 topologies and looked like it showed graph *shape* driving the cost. A 96-configuration sweep across depth, branching factor, and merge factor disproved that: `baseline_pfw == total_nodes - 1` in all 96 configs, zero exceptions. Shape didn't matter. Size did.

---

## Results

Condensed from an actual `run_all.py` run (full output in `results.json`):

| Scenario | Baseline | Validity-aware |
|---|---|---|
| C — stable world | 5 steps, 0 overhead | 5 steps, 0 overhead |
| A — value change | 9 steps, 2 doomed actions | 6 steps, 0 doomed actions |
| D1/D2 — 96 configs | PFW = total_nodes − 1, always | PFW = 0, always |
| D3 — 8 isolated branches | 7 doomed actions (fixed, plan grows 8 → 50 nodes) | 0 doomed actions |
| E1 — real change | 7 steps | 6 steps, 1 verification |
| E2 — false alarm | 3 steps | 4 steps, 1 verification |
| Budget sweep (budgets 6–8) | fails | completes |

E2 is deliberate: it's the one row where validity-aware spends more than it needed to. Without a case where the mechanism loses, the other six rows wouldn't be worth trusting.

---

## Metrics

| Metric | What it measures |
|---|---|
| **Pre-Failure Work (PFW)** | Primary. Non-terminal steps executed after a dependency became invalid but before the failure was detected. "Doomed work." |
| **SCUR** (Stale Context Utilization Rate) | Structural. Proportion of decisions whose dependency set was, at that moment, actually invalidated, computed from ground truth, not from either executor's belief, so it measures real exposure rather than self-reported caution. A verification triggered by an ambiguous/possibly-stale dependency does NOT itself count as stale-context exposure when the underlying fact turns out still valid, which is why Scenario E2 shows SCUR=0.00 for both executors even though validity-aware paid for a verification there. The entire calculation lives in two places: `world.is_doomed()` in `world.py`, and the `decisions_on_stale` counters in `run_baseline`/`run_validity_aware` in `executors.py`. |
| **Recovery (`completed`)** | Outcome. Whether the task finished within its step budget after recovering from invalidation. Flat at 100%/100% under the generously-derived default budget, but the budget sweep on Scenario A shows a real separation window (budgets 6–8) once the budget is externally tightened. |
| **Verification Count** | Supporting. Only meaningful in Scenario E — how many times the validity-aware executor paid to check an ambiguous fact. |
| **Execution Overhead** | Control statistic. Extra steps the validity mechanism costs in Scenario C, where nothing ever actually changes. Confirmed at 0. |

---

## Configuration Reference

The three topology generators, and the budget formula that ties to them:

```python
generate_chain(depth, root_fact="F1")
generate_branching(depth, branching_factor=2, merge_factor=2, root_fact="F1", seed=0)
generate_multi_branch(pre_merge_depth, num_branches, post_merge_depth)

compute_budget(graph, root_fact)
# = len(graph.steps) + graph.invalidated_closure_size(root_fact) + 1
# computed once, before any fault fires, from structure alone
```

`generate_chain` and `generate_branching` share one root fact, so any invalidation touches the entire graph — that's what the closed-form law and the 96-config sweep are built on. `generate_multi_branch` gives each branch its own private fact, so invalidating one only exposes that branch plus the shared merge segment. That's the one generator in this repo where exposure genuinely decouples from total graph size.

---

## Project Structure

```
context-validity-benchmark/
├── context_validity/
│   ├── __init__.py       # Package docstring, no public API surface beyond the modules below
│   ├── facts.py          # Fact + ValidityState (ACTIVE/STALE/SUPERSEDED/UNKNOWN)
│   ├── graph.py          # DependencyGraph, Step, and the three topology generators
│   ├── world.py          # TaskWorld: live facts, scheduled events, ground-truth/belief split
│   ├── executors.py      # run_baseline, run_validity_aware, TaskResult, compute_budget
│   └── scenarios.py      # All 7 named scenarios + the grid sweep + the budget sweep
├── run_all.py            # Runs every scenario, prints tables, writes results.json
├── verify_pfw_law.py     # Analytically derives PFW from graph structure, checks 15 cases
├── make_figures.py       # Renders the 4 article figures from results.json (needs matplotlib)
├── make_charts.py        # Renders ASCII bar charts from results.json, zero dependencies
├── results.json          # Generated by run_all.py — the full numeric output of every scenario
├── figures/              # Generated by make_figures.py
│   ├── fig0_mechanism.png
│   ├── fig_pfw_vs_size_combined.png
│   ├── d3_isolation.png
│   └── budget_sweep.png
└── README.md
```

---

## When to Use This Pattern

Worth building into an agent system if you have:
- Multi-step plans where actions carry real cost (API spend, side effects, work that can't be cheaply undone)
- Long-running or long-context sessions where the gap between "when a fact was observed" and "when it's acted on" can stretch to minutes or hours
- A hard resource ceiling (token budget, tool-call limit, latency budget) where wasted steps aren't just inefficient, they're the difference between finishing and not

Skip it for:
- Single-shot, single-turn queries with no time for anything to go stale between observation and action
- Cheap, freely-retryable actions, where redoing a failed step costs nothing
- Domains where facts genuinely don't change within a session

---

## Known Limitations

- Recovery cost is a flat simplification: both executors pay the same `closure_size + 1` to recover, regardless of how a real system would actually replan.
- Verification is boolean and free of nuance: a check always resolves fully (confirmed or rejected) at a flat one-step cost. Real verification often returns partial or probabilistic information.
- `generate_multi_branch`'s branches are plain chains internally, so breadth exactly equals depth for the invalidated branch. It decouples exposure from total plan size, but not from depth within a single branch.
- This is intentionally not an LLM benchmark. Both executors are small deterministic state machines, not open-ended planners, chosen specifically to isolate the state-validity mechanism before introducing model variability. A real LLM-based version is future work, not a claim made here.

---

## Related Reading

- **[Context Windows Don’t Know What’s Still True — I Built a System That Does](https://towardsdatascience.com/author/emmimalp.alexander/)**
- **[Changing One Prompt Can Affect 50 Others — I Built a Prompt Dependency Graph to Find What Needs Retesting](https://towardsdatascience.com/changing-one-prompt-can-affect-50-others-i-built-a-prompt-dependency-graph-to-find-what-needs-retesting/)**

## License

MIT
