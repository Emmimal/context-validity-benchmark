"""
Render simple ASCII bar charts from results.json. No matplotlib, no
external dependency -- just the standard library, consistent with the
rest of this benchmark.

    python run_all.py
    python make_charts.py
"""

import json


def bar(value, max_value, width=50):
    if max_value == 0:
        filled = 0
    else:
        filled = int(round((value / max_value) * width))
    return "#" * filled + "-" * (width - filled)


def chart_depth_sweep(data):
    runs = data["runs"]
    max_pfw = max(r["baseline_pfw"] for r in runs) or 1
    print("Pre-Failure Work (PFW) vs. dependency depth -- pure chain")
    print("(baseline: late/execution-time detection; validity-aware: early detection)\n")
    for r in runs:
        depth = r["depth"]
        b = r["baseline_pfw"]
        v = r["validity_pfw"]
        print(f"depth={depth:>2}  baseline       [{bar(b, max_pfw)}] {b}")
        print(f"depth={depth:>2}  validity_aware [{bar(v, max_pfw)}] {v}")
    print()


def chart_topologies(data):
    runs = data["runs"]
    max_pfw = max(r["baseline"]["pre_failure_work"] for r in runs) or 1
    print("Pre-Failure Work (PFW) by topology -- breadth vs. depth")
    print("(invalidation depth = longest propagation chain in hops,")
    print(" invalidation breadth = total steps affected)\n")
    for r in runs:
        label = r["topology"]
        b_pfw = r["baseline"]["pre_failure_work"]
        v_pfw = r["validity_aware"]["pre_failure_work"]
        print(f"{label:<26} depth={r['invalidation_depth']:>2} breadth={r['invalidation_breadth']:>3}")
        print(f"  baseline       [{bar(b_pfw, max_pfw)}] {b_pfw}")
        print(f"  validity_aware [{bar(v_pfw, max_pfw)}] {v_pfw}")
    print()


def main():
    with open("results.json") as f:
        data = json.load(f)

    scenarios = {s["name"]: s for s in data["scenarios"]}

    if "D1_depth_sweep" in scenarios:
        chart_depth_sweep(scenarios["D1_depth_sweep"])

    if "D2_topologies" in scenarios:
        chart_topologies(scenarios["D2_topologies"])


if __name__ == "__main__":
    main()
