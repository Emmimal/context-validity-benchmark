"""
Generates the figures for the article from results.json.

This is the ONE place in the whole project that uses a dependency
outside the standard library (matplotlib). The benchmark itself
(everything under context_validity/, run_all.py, verify_pfw_law.py)
remains zero-dependency by design -- this script only turns already-
computed results into images for the write-up.

    python run_all.py       # must run first, produces results.json
    python make_figures.py  # reads results.json, writes figures/*.png
"""

import json
import os

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

OUT_DIR = "figures"


def fig0_mechanism():
    """Conceptual diagram: how the two executors diverge after the same
    world change. This is the article's Figure 1 -- the mechanism,
    before any numbers."""
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    def box(x, y, w, h, text, color="#eaeaea", fontsize=10):
        b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", linewidth=1.2,
                            edgecolor="#333333", facecolor=color)
        ax.add_patch(b)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, wrap=True)

    def arrow(x1, y1, x2, y2, color="#333333"):
        a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14,
                             linewidth=1.4, color=color)
        ax.add_patch(a)

    box(3, 10.2, 4, 1.1, "10:00  Price = $420", "#dbe9f4")
    arrow(5, 10.2, 5, 9.3)
    box(3, 8.2, 4, 1.1, "10:01  Plan created\n(book at $420)", "#dbe9f4")
    arrow(5, 8.2, 5, 7.3)
    box(3, 6.2, 4, 1.1, "10:03  Price = $610", "#f4dbdb")
    arrow(5, 6.2, 2.6, 5.1)
    arrow(5, 6.2, 7.4, 5.1)

    box(0.3, 3.6, 4.6, 1.3, "BASELINE\nexecutes anyway\n(late detection)", "#f8d7d7")
    arrow(2.6, 3.6, 2.6, 2.7)
    box(0.3, 1.4, 4.6, 1.1, "doomed work,\nthen failure -> replan", "#f0b8b8")

    box(5.1, 3.6, 4.6, 1.3, "VALIDITY-AWARE\nchecks dependency first\n(early detection)", "#d7ecd7")
    arrow(7.4, 3.6, 7.4, 2.7)
    box(5.1, 1.4, 4.6, 1.1, "replan immediately,\nzero doomed work", "#b8e0b8")

    ax.set_title("How the two executors diverge after the same world change", fontsize=12)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/fig0_mechanism.png", dpi=150)
    plt.close(fig)


def fig_pfw_vs_size_combined():
    """D1's chain + D2's three topologies + the full 96-config sweep,
    all on one PFW-vs-affected-size chart. Replaces the separate D1
    and D2 bar charts with a single, much stronger visual proof of
    the closed-form law."""
    from context_validity.scenarios import scenario_D_cascade_chain, topology_parameter_grid

    d1_points = []
    for depth in [1, 2, 3, 5, 10]:
        b, v = scenario_D_cascade_chain(depth=depth, change_tick=0)
        d1_points.append((depth, b.pre_failure_work, v.pre_failure_work))

    grid = topology_parameter_grid(depths=[3, 4, 5, 6, 7, 8], branching_factors=[1, 2, 3, 4], merge_factors=[1, 2, 3, 4], seed=0)
    grid_x = [r["total_nodes"] for r in grid]
    grid_y_b = [r["baseline_pfw"] for r in grid]
    grid_y_v = [r["validity_pfw"] for r in grid]

    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.scatter(grid_x, grid_y_b, alpha=0.35, s=35, color="#c0392b", label="Baseline (96-config sweep)")
    ax.scatter(grid_x, grid_y_v, alpha=0.35, s=35, color="#2471a3", label="Validity-aware (96-config sweep)")

    d1_x = [p[0] for p in d1_points]
    d1_yb = [p[1] for p in d1_points]
    d1_yv = [p[2] for p in d1_points]
    ax.plot(d1_x, d1_yb, marker="o", color="#7b241c", linewidth=1.5, label="D1 chain (baseline)")
    ax.plot(d1_x, d1_yv, marker="o", color="#1a5276", linewidth=1.5, label="D1 chain (validity-aware)")

    xs = np.linspace(1, max(grid_x), 50)
    ax.plot(xs, xs - 1, linestyle="--", color="black", linewidth=1, alpha=0.6, label="PFW = size - 1 (the law)")

    ax.set_xlabel("Total nodes affected by the invalidated fact")
    ax.set_ylabel("Pre-Failure Work (PFW)")
    ax.set_title("One relationship, not three: PFW tracks affected size exactly\n(D1 chain + D2 topologies + full 96-config sweep, all on the same line)")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/fig_pfw_vs_size_combined.png", dpi=150)
    plt.close(fig)


def fig_d3_isolation(data):
    runs = data["runs"]
    branch_counts = [1, 4, 8]
    pct = [r["breadth_pct"] for r in runs]
    breadth = [r["invalidation_breadth"] for r in runs]

    fig, ax1 = plt.subplots(figsize=(6.5, 4.5))
    ax1.bar([str(b) for b in branch_counts], pct, color="#7d3c98", alpha=0.85)
    ax1.set_xlabel("Number of independent branches")
    ax1.set_ylabel("Plan exposed to one broken fact (%)", color="#7d3c98")
    ax1.set_ylim(0, 105)
    for i, p in enumerate(pct):
        ax1.text(i, p + 2, f"{p:.1f}%", ha="center", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot([str(b) for b in branch_counts], breadth, marker="o", color="#1a5276", linewidth=2)
    ax2.set_ylabel("Absolute invalidation breadth (steps)", color="#1a5276")
    ax2.set_ylim(0, max(breadth) + 3)

    ax1.set_title("D3: isolating a fact shrinks its exposure fraction\neven though its absolute footprint stays fixed")
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/d3_isolation.png", dpi=150)
    plt.close(fig)


def fig_budget_sweep(rows):
    budgets = [r["budget"] for r in rows]
    baseline = [1 if r["baseline_completed"] else 0 for r in rows]
    validity = [1 if r["validity_completed"] else 0 for r in rows]

    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.step(budgets, baseline, where="mid", label="Baseline", color="#c0392b", linewidth=2.5)
    ax.step(budgets, validity, where="mid", label="Validity-aware", color="#2471a3", linewidth=2.5, linestyle="--")
    ax.set_xlabel("Step budget")
    ax.set_ylabel("Task completed (1 = yes)")
    ax.set_yticks([0, 1])
    ax.set_title("Budget sweep: stale context can cost the task, not just steps\n(separation window at budgets 6-8)")
    ax.invert_xaxis()
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{OUT_DIR}/budget_sweep.png", dpi=150)
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open("results.json") as f:
        data = json.load(f)
    scenarios = {s["name"]: s for s in data["scenarios"]}

    fig0_mechanism()
    fig_pfw_vs_size_combined()
    if "D3_isolated_branches" in scenarios:
        fig_d3_isolation(scenarios["D3_isolated_branches"])

    budget_rows = data.get("robustness_checks", {}).get("budget_sweep_A")
    if budget_rows:
        fig_budget_sweep(budget_rows)

    print(f"Figures written to {OUT_DIR}/")


if __name__ == "__main__":
    main()
