"""
Run every scenario in the context-validity benchmark and print result
tables. Pure standard library -- no API, no LLM, no external packages.

    python run_all.py
"""

import json
from dataclasses import asdict

from context_validity.scenarios import (
    budget_sweep_A,
    scenario_A_value_change,
    scenario_C_control,
    scenario_D_cascade_chain,
    scenario_D_topology,
    scenario_D3_isolated_branch,
    scenario_E_ambiguous,
    topology_parameter_grid,
)


def _row(label, r):
    return (
        f"{label:<22} {r.executor:<15} {str(r.completed):<10} "
        f"{r.steps_used:>6} {r.budget:>7} {r.replans:>8} "
        f"{r.verifications:>8} {r.pre_failure_work:>5} {r.scur:>7.2f}"
    )


def _header():
    return (
        f"{'Scenario':<22} {'Executor':<15} {'Completed':<10} "
        f"{'Steps':>6} {'Budget':>7} {'Replans':>8} "
        f"{'Verifs':>8} {'PFW':>5} {'SCUR':>7}"
    )


def print_pair(label, baseline, validity):
    print(_row(label, baseline))
    print(_row(label, validity))


def pfw_reduction_pct(baseline_pfw, validity_pfw):
    if baseline_pfw == 0:
        return None
    return round((baseline_pfw - validity_pfw) / baseline_pfw * 100, 1)


def main():
    results = {"scenarios": []}

    print("=" * 100)
    print("SCENARIO C -- Control (stable world, nothing changes)")
    print("Purpose: measure Execution Overhead -- what the validity mechanism")
    print("costs when it has nothing to catch. Expect steps_used to match.")
    print("=" * 100)
    print(_header())
    b, v = scenario_C_control(depth=5)
    print_pair("C: control", b, v)
    overhead = v.steps_used - b.steps_used
    print(f"\nExecution Overhead (validity_aware - baseline steps_used): {overhead}")
    results["scenarios"].append({"name": "C_control", "baseline": asdict(b), "validity_aware": asdict(v), "execution_overhead": overhead})

    print()
    print("=" * 100)
    print("SCENARIO A -- Value change ($420 -> $610) on a short chain")
    print("Purpose: the basic early-vs-late detection proof of concept.")
    print("=" * 100)
    print(_header())
    b, v = scenario_A_value_change(depth=4, change_tick=1)
    print_pair("A: value change", b, v)
    results["scenarios"].append({"name": "A_value_change", "baseline": asdict(b), "validity_aware": asdict(v)})

    print()
    print("=" * 100)
    print("SCENARIO D1 -- Depth-scaling characterization (pure chain)")
    print("NOTE: on a pure chain this relationship follows directly from the")
    print("policy definitions (baseline PFW ~ depth-1, validity-aware PFW ~ 0).")
    print("This is reported as a characterization, not presented as a discovery.")
    print("=" * 100)
    print(_header())
    depth_sweep_results = []
    for depth in [1, 2, 3, 5, 10]:
        b, v = scenario_D_cascade_chain(depth=depth, change_tick=0)
        print_pair(f"D1: chain depth={depth}", b, v)
        depth_sweep_results.append({"depth": depth, "baseline_pfw": b.pre_failure_work, "validity_pfw": v.pre_failure_work})
    results["scenarios"].append({"name": "D1_depth_sweep", "runs": depth_sweep_results})

    print()
    print("=" * 100)
    print("SCENARIO D2 -- Global invalidation: affected-subgraph size scaling")
    print("Purpose: characterize how doomed work scales with the size of the affected")
    print("executable graph under global invalidation (a single fact shared by the")
    print("whole graph). InvDepth/InvBreadth are reported as structural descriptors,")
    print("NOT as evidence that topology shape itself drives PFW -- a 96-config sweep")
    print("(see ROBUSTNESS CHECKS below) already showed baseline_pfw = total_nodes - 1")
    print("regardless of shape. D3 is where shape/isolation actually matters.")
    print("=" * 100)
    print(f"{'Topology':<24} {'InvDepth':>9} {'InvBreadth':>11}")
    topologies = [
        ("chain (depth=6)", dict(depth=6, branching_factor=1, merge_factor=1)),
        ("shallow/wide (d=4,bf=4)", dict(depth=4, branching_factor=4, merge_factor=4)),
        ("deep/branching (d=8,bf=2)", dict(depth=8, branching_factor=2, merge_factor=2)),
    ]
    topo_runs = []
    for label, params in topologies:
        b, v, inv_depth, inv_breadth = scenario_D_topology(seed=0, **params)
        print(f"{label:<24} {inv_depth:>9} {inv_breadth:>11}")
        topo_runs.append((label, inv_depth, inv_breadth, b, v))
    print()
    print(_header())
    topo_results = []
    for label, inv_depth, inv_breadth, b, v in topo_runs:
        print_pair(label, b, v)
        topo_results.append({
            "topology": label,
            "invalidation_depth": inv_depth,
            "invalidation_breadth": inv_breadth,
            "baseline": asdict(b),
            "validity_aware": asdict(v),
        })
    results["scenarios"].append({"name": "D2_topologies", "runs": topo_results})

    print()
    print("=" * 100)
    print("SCENARIO D3 -- Isolated branches (breadth genuinely decoupled from graph size)")
    print("Purpose: invalidate ONE branch's private fact and show that the fraction of")
    print("the plan exposed shrinks as the plan is split into more independent branches,")
    print("even though that failure's own depth and absolute breadth stay fixed.")
    print("NOTE: in this generator each branch is a plain chain (no internal fan-out),")
    print("so breadth == depth for the invalidated branch here -- this experiment proves")
    print("size-independence, not breadth-vs-depth independence (that's what D2 showed).")
    print("=" * 100)
    print(f"{'Config':<28} {'TotalNodes':>10} {'InvDepth':>9} {'InvBreadth':>11} {'Breadth%':>9} {'BaselinePFW':>12}")
    d3_configs = [
        ("1 branch (= chain)", dict(pre_merge_depth=6, num_branches=1, post_merge_depth=2)),
        ("4 branches", dict(pre_merge_depth=6, num_branches=4, post_merge_depth=2)),
        ("8 branches", dict(pre_merge_depth=6, num_branches=8, post_merge_depth=2)),
    ]
    d3_results = []
    for label, params in d3_configs:
        b, v, inv_depth, inv_breadth, total = scenario_D3_isolated_branch(**params)
        pct = 100 * inv_breadth / total
        print(f"{label:<28} {total:>10} {inv_depth:>9} {inv_breadth:>11} {pct:>8.1f}% {b.pre_failure_work:>12}")
        d3_results.append({
            "config": label, "total_nodes": total, "invalidation_depth": inv_depth,
            "invalidation_breadth": inv_breadth, "breadth_pct": pct,
            "baseline": asdict(b), "validity_aware": asdict(v),
        })
    results["scenarios"].append({"name": "D3_isolated_branches", "runs": d3_results})

    print()
    print("=" * 100)
    print("SCENARIO E -- Ambiguous state: E1 (real change) vs E2 (false alarm)")
    print("Purpose: expose the verification cost/benefit trade-off. E2 is the")
    print("case where validity-aware is allowed to do MORE work than baseline.")
    print("=" * 100)
    print(_header())
    b1, v1 = scenario_E_ambiguous(ground_truth_changed=True, depth=3, change_tick=1)
    print_pair("E1: real change", b1, v1)
    b2, v2 = scenario_E_ambiguous(ground_truth_changed=False, depth=3, change_tick=1)
    print_pair("E2: false alarm", b2, v2)
    results["scenarios"].append({
        "name": "E_ambiguous",
        "E1_real_change": {"baseline": asdict(b1), "validity_aware": asdict(v1)},
        "E2_false_alarm": {"baseline": asdict(b2), "validity_aware": asdict(v2)},
    })
    print(f"\nE2 steps_used -- baseline: {b2.steps_used}, validity_aware: {v2.steps_used} "
          f"(validity_aware costs {v2.steps_used - b2.steps_used} extra step(s) for a false alarm)")

    print()
    print("=" * 100)
    print("ROBUSTNESS CHECKS (run before writing the article, not for the main tables)")
    print("=" * 100)

    print("\n[1] PFW Reduction % (baseline_pfw - validity_pfw) / baseline_pfw:")
    a_b, a_v = scenario_A_value_change(depth=4, change_tick=1)
    print(f"  Scenario A:  {pfw_reduction_pct(a_b.pre_failure_work, a_v.pre_failure_work)}%")
    chain5_b, chain5_v = scenario_D_cascade_chain(depth=5, change_tick=0)
    print(f"  D1 depth=5:  {pfw_reduction_pct(chain5_b.pre_failure_work, chain5_v.pre_failure_work)}%")
    topo_b, topo_v, _, _ = scenario_D_topology(depth=4, branching_factor=4, merge_factor=4, seed=0)
    print(f"  D2 shallow/wide: {pfw_reduction_pct(topo_b.pre_failure_work, topo_v.pre_failure_work)}%")
    print("  (For every nonzero-PFW case in this benchmark, this is 100% -- validity-aware")
    print("   eliminates doomed work entirely by construction, not partially. Report it as")
    print("   'zero doomed actions' rather than 'N% faster', since total step count also")
    print("   includes the identical recovery cost both executors pay once they replan.)")

    print("\n[2] Topology parameter grid (depth 3-8 x branching_factor 1-4 x merge_factor 1-4):")
    grid = topology_parameter_grid(depths=[3, 4, 5, 6, 7, 8], branching_factors=[1, 2, 3, 4], merge_factors=[1, 2, 3, 4], seed=0)
    mismatches = [r for r in grid if r["baseline_pfw"] != r["total_nodes"] - 1]
    print(f"  {len(grid)} configs tested. baseline_pfw != total_nodes - 1 in {len(mismatches)} of them.")
    print("  FINDING: for this single-root generator, baseline PFW is a pure function of")
    print("  total graph size (PFW = total_nodes - 1), independent of shape (depth vs.")
    print("  branching_factor vs. merge_factor). D2's 'shape matters' framing should be")
    print("  corrected to 'size matters' -- D3 (isolated branches) is where shape/isolation")
    print("  actually changes the exposed fraction independent of size.")

    print("\n[3] Budget sweep on Scenario A (depth=4) -- does Recovery Rate ever separate?")
    sweep = budget_sweep_A(depth=4, change_tick=1)
    print(f"  {'Budget':>7} {'Baseline completed':>19} {'Validity completed':>19}")
    for r in sweep:
        print(f"  {r['budget']:>7} {str(r['baseline_completed']):>19} {str(r['validity_completed']):>19}")
    print("  FINDING: real separation window at budgets 6-8 -- validity-aware recovers,")
    print("  baseline doesn't (it needs its full natural budget of 9 to pay for both the")
    print("  wasted work AND the recovery). This budget was not tuned to produce this --")
    print("  it's the natural result of sweeping below the baseline's as-built cost.")
    print("  Recovery Rate is meaningful under resource pressure, flat (100%/100%) otherwise.")

    results["robustness_checks"] = {
        "pfw_reduction_pct": {
            "scenario_A": pfw_reduction_pct(a_b.pre_failure_work, a_v.pre_failure_work),
            "D1_depth5": pfw_reduction_pct(chain5_b.pre_failure_work, chain5_v.pre_failure_work),
            "D2_shallow_wide": pfw_reduction_pct(topo_b.pre_failure_work, topo_v.pre_failure_work),
        },
        "topology_grid_size": len(grid),
        "topology_grid_pfw_equals_size_minus_1": len(mismatches) == 0,
        "budget_sweep_A": sweep,
    }

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nFull results written to results.json")


if __name__ == "__main__":
    main()
