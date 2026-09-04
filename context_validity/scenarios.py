"""
The four featured scenarios (C, A, D, E), plus the depth-sweep and
topology-comparison helpers used for the characterization experiment.

Every scenario is fully deterministic: no random sampling of
outcomes. The only randomness anywhere in this package is the
(seeded) wiring of branching topologies, which is fixed and
reproducible given a seed.
"""

from typing import Dict

from .executors import compute_budget, run_baseline, run_validity_aware
from .facts import Fact
from .graph import generate_branching, generate_chain, generate_multi_branch
from .world import InvalidationEvent, TaskWorld


def _fresh_facts(root_fact: str = "F1", value=420) -> Dict[str, Fact]:
    return {root_fact: Fact(id=root_fact, value=value)}


def scenario_C_control(depth: int = 5):
    """Stable world: nothing changes at all. This measures Execution
    Overhead -- the cost the validity mechanism adds when it has
    nothing to catch. Expected result: baseline and validity-aware
    should use exactly the same number of steps."""
    graph = generate_chain(depth)
    budget = compute_budget(graph, "F1")

    world_b = TaskWorld(facts=_fresh_facts(), events=[])
    world_v = TaskWorld(facts=_fresh_facts(), events=[])

    baseline = run_baseline(graph, world_b, "F1", budget)
    validity = run_validity_aware(graph, world_v, "F1", budget)
    return baseline, validity


def scenario_A_value_change(depth: int = 4, change_tick: int = 1, budget_override: int = None):
    """Flight A: $420 -> $610, partway through a short chain. The
    basic proof of the early-vs-late detection mechanism."""
    graph = generate_chain(depth)
    budget = budget_override if budget_override is not None else compute_budget(graph, "F1")

    events = [InvalidationEvent(tick=change_tick, fact_id="F1", kind="replace", new_value=610)]
    world_b = TaskWorld(facts=_fresh_facts(value=420), events=list(events))
    world_v = TaskWorld(facts=_fresh_facts(value=420), events=list(events))

    baseline = run_baseline(graph, world_b, "F1", budget)
    validity = run_validity_aware(graph, world_v, "F1", budget)
    return baseline, validity


def scenario_D_cascade_chain(depth: int, change_tick: int = 0):
    """Depth-scaling characterization on a pure chain. We do NOT
    frame this as a discovery: on a non-branching chain, baseline PFW
    is a direct restatement of the policy definitions (roughly
    depth - 1), and validity-aware PFW is ~0 by construction. The
    point of running it is to show the mechanical shape of that
    relationship plainly, not to claim it as an emergent finding."""
    graph = generate_chain(depth)
    budget = compute_budget(graph, "F1")

    events = [InvalidationEvent(tick=change_tick, fact_id="F1", kind="replace", new_value="unavailable")]
    world_b = TaskWorld(facts=_fresh_facts(value="available"), events=list(events))
    world_v = TaskWorld(facts=_fresh_facts(value="available"), events=list(events))

    baseline = run_baseline(graph, world_b, "F1", budget)
    validity = run_validity_aware(graph, world_v, "F1", budget)
    return baseline, validity


def scenario_D_topology(depth: int, branching_factor: int, merge_factor: int, seed: int = 0, change_tick: int = 0, budget_override: int = None):
    """The genuinely interesting version of D: a branching/merging
    topology, where invalidation depth and invalidation breadth are
    separate, measurable quantities rather than being tied together
    the way they are in a pure chain."""
    graph = generate_branching(depth, branching_factor, merge_factor, seed=seed)
    budget = budget_override if budget_override is not None else compute_budget(graph, "F1")

    events = [InvalidationEvent(tick=change_tick, fact_id="F1", kind="replace", new_value="unavailable")]
    world_b = TaskWorld(facts=_fresh_facts(value="available"), events=list(events))
    world_v = TaskWorld(facts=_fresh_facts(value="available"), events=list(events))

    baseline = run_baseline(graph, world_b, "F1", budget)
    validity = run_validity_aware(graph, world_v, "F1", budget)

    invalidation_depth = graph.invalidation_depth("F1")
    invalidation_breadth = graph.invalidated_closure_size("F1")
    return baseline, validity, invalidation_depth, invalidation_breadth


def topology_parameter_grid(depths, branching_factors, merge_factors, seed: int = 0):
    """Sweep a grid of (depth, branching_factor, merge_factor) combos
    instead of 3 hand-picked topologies. NOTE: seed is included only
    to make a point -- for the single-root branching generator, seed
    provably does not change breadth or PFW (every node inherits the
    root fact regardless of wiring), so this grid varies the
    structural parameters, not the seed, to actually produce
    variation. Returns a list of result dicts.
    """
    rows = []
    for depth in depths:
        for bf in branching_factors:
            for mf in merge_factors:
                b, v, inv_depth, inv_breadth = scenario_D_topology(
                    depth=depth, branching_factor=bf, merge_factor=mf, seed=seed
                )
                rows.append({
                    "depth": depth, "branching_factor": bf, "merge_factor": mf,
                    "total_nodes": inv_breadth,  # == total nodes for single-root generator
                    "invalidation_depth": inv_depth,
                    "invalidation_breadth": inv_breadth,
                    "baseline_pfw": b.pre_failure_work,
                    "validity_pfw": v.pre_failure_work,
                })
    return rows


def budget_sweep_A(depth: int = 4, change_tick: int = 1, budgets=None):
    """Re-run Scenario A under a range of externally fixed budgets
    (not the computed principled one) to see whether Recovery Rate
    (completed vs. not) actually separates baseline from
    validity-aware once the budget gets tight enough to matter."""
    if budgets is None:
        graph = generate_chain(depth)
        natural = compute_budget(graph, "F1")
        budgets = list(range(natural, max(natural - 6, 0), -1))
    rows = []
    for budget in budgets:
        b, v = scenario_A_value_change(depth=depth, change_tick=change_tick, budget_override=budget)
        rows.append({"budget": budget, "baseline_completed": b.completed, "validity_completed": v.completed})
    return rows


def scenario_D3_isolated_branch(pre_merge_depth: int, num_branches: int, post_merge_depth: int, change_tick: int = 0):
    """The genuinely decoupled version of the cascade experiment.
    Several independent branches share one merge-and-action segment.
    Invalidating ONE branch's private fact should only expose that
    branch's own steps plus the shared segment -- NOT the other
    branches' private steps. Breadth as a fraction of total graph
    size should shrink as num_branches grows, even though the
    invalidation *depth* (pre_merge_depth + post_merge_depth) stays
    fixed -- this is what demonstrates breadth and depth as genuinely
    separate quantities, rather than breadth always equalling total
    graph size regardless of topology shape.
    """
    graph, branch_facts = generate_multi_branch(pre_merge_depth, num_branches, post_merge_depth)
    invalidated_fact = branch_facts[0]
    total_nodes = len(graph.steps)
    budget = compute_budget(graph, invalidated_fact)

    events = [InvalidationEvent(tick=change_tick, fact_id=invalidated_fact, kind="replace", new_value="broken")]
    facts_b = {f: Fact(id=f, value="ok") for f in branch_facts}
    facts_v = {f: Fact(id=f, value="ok") for f in branch_facts}
    world_b = TaskWorld(facts=facts_b, events=list(events))
    world_v = TaskWorld(facts=facts_v, events=list(events))

    baseline = run_baseline(graph, world_b, invalidated_fact, budget)
    validity = run_validity_aware(graph, world_v, invalidated_fact, budget)

    inv_depth = graph.invalidation_depth(invalidated_fact)
    inv_breadth = graph.invalidated_closure_size(invalidated_fact)
    return baseline, validity, inv_depth, inv_breadth, total_nodes


def scenario_E_ambiguous(ground_truth_changed: bool, depth: int = 3, change_tick: int = 1):
    """E1 (ground_truth_changed=True): the ambiguous signal turns out
    to be a real change -- verification should trigger a replan.

    E2 (ground_truth_changed=False): a false alarm -- verification
    should confirm the fact is still fine. This costs the
    validity-aware executor one verification step for nothing, while
    the baseline (which never reacted to the ambiguity at all) pays
    nothing. E2 exists specifically so the benchmark can show
    validity-aware doing *more* work than baseline in a legitimate
    case, rather than being designed to always win.
    """
    graph = generate_chain(depth)
    budget = compute_budget(graph, "F1")

    events = [
        InvalidationEvent(
            tick=change_tick,
            fact_id="F1",
            kind="ambiguous",
            ground_truth_changed=ground_truth_changed,
        )
    ]
    world_b = TaskWorld(facts=_fresh_facts(), events=list(events))
    world_v = TaskWorld(facts=_fresh_facts(), events=list(events))

    baseline = run_baseline(graph, world_b, "F1", budget)
    validity = run_validity_aware(graph, world_v, "F1", budget)
    return baseline, validity
