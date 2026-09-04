"""
Verifies the closed-form law that governs Pre-Failure Work across every
scenario in this benchmark:

    baseline_pfw = number of non-action steps in the invalidated fact's
                   requires_closure that have NOT yet executed at the
                   moment the fact breaks.

For any scenario where the break happens before the plan starts (D1, D2,
D3 all use change_tick=0), this collapses to `closure_size - 1`. For
scenarios where the break happens mid-plan (A, E), it's reduced by
however many closure steps already executed safely before the break.

This is not a new experiment -- it's a check that the entire D-family
of results (D1/D2/D3) are different views of ONE mechanical law, not
three independent empirical findings. Run this after any change to
graph.py, world.py, or executors.py to confirm the law still holds.

    python verify_pfw_law.py
"""

from context_validity.graph import generate_branching, generate_chain, generate_multi_branch
from context_validity.scenarios import (
    scenario_A_value_change,
    scenario_D_cascade_chain,
    scenario_D_topology,
    scenario_D3_isolated_branch,
)


def expected_pfw(graph, root_fact, change_tick):
    """Analytically derive PFW from the graph and break timing alone,
    without running either executor."""
    order = graph.topological_order()
    count = 0
    for i, step_id in enumerate(order):
        step = graph.steps[step_id]
        if root_fact not in step.requires_closure:
            continue
        if i < change_tick:  # already executed before the break (1 tick/step)
            continue
        if step.is_action:
            continue
        count += 1
    return count


def main():
    tests = []

    for depth in [1, 2, 3, 5, 10]:
        g = generate_chain(depth)
        b, _ = scenario_D_cascade_chain(depth=depth, change_tick=0)
        tests.append((f"D1 chain depth={depth}", expected_pfw(g, "F1", 0), b.pre_failure_work))

    g = generate_chain(4)
    for tick in [0, 1, 2, 3]:
        b, _ = scenario_A_value_change(depth=4, change_tick=tick)
        tests.append((f"A depth=4 tick={tick}", expected_pfw(g, "F1", tick), b.pre_failure_work))

    for label, params in [
        ("chain-equivalent", dict(depth=6, branching_factor=1, merge_factor=1)),
        ("shallow/wide", dict(depth=4, branching_factor=4, merge_factor=4)),
        ("deep/branching", dict(depth=8, branching_factor=2, merge_factor=2)),
    ]:
        g = generate_branching(**params, seed=0)
        b, _, _, _ = scenario_D_topology(seed=0, **params)
        tests.append((f"D2 {label}", expected_pfw(g, "F1", 0), b.pre_failure_work))

    for label, params in [
        ("1 branch", dict(pre_merge_depth=6, num_branches=1, post_merge_depth=2)),
        ("4 branches", dict(pre_merge_depth=6, num_branches=4, post_merge_depth=2)),
        ("8 branches", dict(pre_merge_depth=6, num_branches=8, post_merge_depth=2)),
    ]:
        g, branch_facts = generate_multi_branch(**params)
        b, _, _, _, _ = scenario_D3_isolated_branch(**params)
        tests.append((f"D3 {label}", expected_pfw(g, branch_facts[0], 0), b.pre_failure_work))

    print(f"{'Case':<24} {'Expected':>8} {'Actual':>8} {'Match':>7}")
    all_match = True
    for label, expected, actual in tests:
        match = expected == actual
        all_match &= match
        print(f"{label:<24} {expected:>8} {actual:>8} {str(match):>7}")

    print()
    print(f"ALL {len(tests)} CASES MATCH THE CLOSED-FORM LAW: {all_match}")
    assert all_match, "PFW no longer matches the closed-form law -- check recent changes to graph.py/world.py/executors.py"


if __name__ == "__main__":
    main()
