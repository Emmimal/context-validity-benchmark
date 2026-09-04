"""
Dependency graph of Steps (plan / decision / action operations) over
Facts.

A Step's `requires_closure` is the full set of facts it depends on,
including everything inherited transitively from its structural
predecessors. This is what lets an invalidation propagate through the
graph instead of only affecting the single node a fact was originally
attached to -- a plan three hops downstream of a broken fact still
"requires" that fact, even though it never mentions it directly.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class Step:
    id: str
    kind: str  # "plan" | "decision" | "action"
    direct_requires: Set[str] = field(default_factory=set)
    predecessors: Set[str] = field(default_factory=set)
    requires_closure: Set[str] = field(default_factory=set)  # filled by build()

    @property
    def is_action(self) -> bool:
        return self.kind == "action"


class DependencyGraph:
    def __init__(self) -> None:
        self.steps: Dict[str, Step] = {}

    def add_step(self, step: Step) -> None:
        self.steps[step.id] = step

    def build(self) -> None:
        """Compute requires_closure for every step in topological order."""
        for step_id in self.topological_order():
            step = self.steps[step_id]
            closure = set(step.direct_requires)
            for pred_id in step.predecessors:
                closure |= self.steps[pred_id].requires_closure
            step.requires_closure = closure

    def topological_order(self) -> List[str]:
        in_degree = {sid: len(s.predecessors) for sid, s in self.steps.items()}
        successors: Dict[str, List[str]] = {sid: [] for sid in self.steps}
        for sid, s in self.steps.items():
            for pred in s.predecessors:
                successors[pred].append(sid)

        ready = sorted(sid for sid, d in in_degree.items() if d == 0)
        order: List[str] = []
        while ready:
            ready.sort()
            current = ready.pop(0)
            order.append(current)
            for succ in successors[current]:
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    ready.append(succ)

        if len(order) != len(self.steps):
            raise ValueError("Cycle detected in dependency graph")
        return order

    def invalidated_closure_size(self, root_fact_id: str) -> int:
        """How many steps have `root_fact_id` in their requires_closure.
        Used both to report invalidation breadth and to size the
        recovery allowance in the step budget."""
        return sum(1 for s in self.steps.values() if root_fact_id in s.requires_closure)

    def invalidation_depth(self, root_fact_id: str) -> int:
        """Longest chain of steps downstream of root_fact_id -- how
        far the invalidation propagates, in hops."""
        order = self.topological_order()
        depth_at: Dict[str, int] = {}
        max_depth = 0
        for sid in order:
            step = self.steps[sid]
            if root_fact_id not in step.requires_closure:
                continue
            preds_in_closure = [depth_at[p] for p in step.predecessors if p in depth_at]
            depth_at[sid] = (max(preds_in_closure) + 1) if preds_in_closure else 1
            max_depth = max(max_depth, depth_at[sid])
        return max_depth


def generate_chain(depth: int, root_fact: str = "F1") -> DependencyGraph:
    """A pure chain: F1 -> S0 -> S1 -> ... -> S(depth-1)[action].

    Deliberately simple. Used for the depth-scaling characterization,
    where the scaling relationship (baseline PFW grows with depth,
    validity-aware stays ~0) follows directly from this topology --
    that is stated openly rather than presented as a discovery.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    g = DependencyGraph()
    prev_id = None
    for i in range(depth):
        kind = "action" if i == depth - 1 else ("plan" if i == 0 else "decision")
        step = Step(
            id=f"S{i}",
            kind=kind,
            direct_requires={root_fact} if i == 0 else set(),
            predecessors={prev_id} if prev_id else set(),
        )
        g.add_step(step)
        prev_id = step.id
    g.build()
    return g


def generate_branching(
    depth: int,
    branching_factor: int = 2,
    merge_factor: int = 2,
    root_fact: str = "F1",
    seed: int = 0,
) -> DependencyGraph:
    """A diamond-shaped topology: branches out from the root fact for
    the first half of `depth` layers, then merges back down to a
    single terminal action. Deterministic given `seed` -- the same
    seed always produces the same wiring.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    rng = random.Random(seed)
    g = DependencyGraph()

    widths: List[int] = []
    width = 1
    for layer in range(depth):
        if layer < depth / 2:
            width = min(width * branching_factor, branching_factor ** 3)
        else:
            width = max(1, width // merge_factor)
        widths.append(width)
    widths[-1] = 1  # force a single terminal action

    prev_layer_nodes: List[str] = []
    for layer_idx, width in enumerate(widths):
        is_last = layer_idx == len(widths) - 1
        this_layer_nodes: List[str] = []
        for j in range(width):
            step_id = f"L{layer_idx}_{j}"
            if layer_idx == 0:
                preds: Set[str] = set()
                direct = {root_fact}
            else:
                n_preds = min(len(prev_layer_nodes), branching_factor)
                preds = set(rng.sample(prev_layer_nodes, n_preds))
                direct = set()
            step = Step(
                id=step_id,
                kind="action" if is_last else ("plan" if layer_idx == 0 else "decision"),
                direct_requires=direct,
                predecessors=preds,
            )
            g.add_step(step)
            this_layer_nodes.append(step_id)
        prev_layer_nodes = this_layer_nodes

    g.build()
    return g


def generate_multi_branch(pre_merge_depth: int, num_branches: int, post_merge_depth: int):
    """Several independent branches, each fed by its OWN private fact,
    joining into a single shared merge-and-terminal-action segment.

    This is what the single-root generators above cannot show: because
    every branch has a distinct fact, invalidating one branch's fact
    only affects that branch's private steps plus the shared segment
    downstream of the merge -- the other branches' private steps are
    untouched. Breadth is therefore no longer forced to equal the
    total node count; it genuinely depends on WHERE the invalidation
    happens (which branch's fact broke), decoupling breadth from both
    depth and overall graph size.

    Returns (graph, branch_fact_ids).
    """
    if pre_merge_depth < 1 or num_branches < 1 or post_merge_depth < 1:
        raise ValueError("pre_merge_depth, num_branches, post_merge_depth must all be >= 1")

    g = DependencyGraph()
    branch_facts = [f"F{i + 1}" for i in range(num_branches)]
    branch_tail_ids: List[str] = []

    for b, fact_id in enumerate(branch_facts):
        prev = None
        for i in range(pre_merge_depth):
            step_id = f"B{b}_{i}"
            step = Step(
                id=step_id,
                kind="plan" if i == 0 else "decision",
                direct_requires={fact_id} if i == 0 else set(),
                predecessors={prev} if prev else set(),
            )
            g.add_step(step)
            prev = step_id
        branch_tail_ids.append(prev)

    prev = None
    for i in range(post_merge_depth):
        step_id = f"M{i}"
        kind = "action" if i == post_merge_depth - 1 else "decision"
        preds = set(branch_tail_ids) if i == 0 else ({prev} if prev else set())
        step = Step(id=step_id, kind=kind, direct_requires=set(), predecessors=preds)
        g.add_step(step)
        prev = step_id

    g.build()
    return g, branch_facts
