"""
The two executors under comparison.

Deliberately not called "agents": each is a small deterministic state
machine, not an LLM, and not an open-ended planner. This is
intentional -- isolating the state-validity mechanism before
introducing model variability. Both executors receive the exact same
task, the same plan, and the same sequence of world events. The only
difference is *when* each one finds out that a dependency no longer
holds:

  Baseline Executor        -- discovers invalidity at execution time
                               (when a downstream Action actually
                               fails in the real world). It is not
                               blind: it always eventually notices.
                               It just pays for everything it did in
                               between.

  Validity-Aware Executor   -- checks dependency status before
                               executing each step, and can act on
                               ACTIVE / STALE / SUPERSEDED / UNKNOWN
                               beliefs. It cannot see ground truth
                               directly -- only through execution or
                               a paid Verify step.
"""

from dataclasses import dataclass

from .facts import ValidityState
from .graph import DependencyGraph
from .world import TaskWorld


@dataclass
class TaskResult:
    executor: str
    completed: bool
    steps_used: int
    budget: int
    replans: int
    verifications: int
    pre_failure_work: int  # PFW: doomed non-action steps executed before detection
    decisions_total: int
    decisions_on_stale_deps: int  # numerator for SCUR

    @property
    def scur(self) -> float:
        if self.decisions_total == 0:
            return 0.0
        return self.decisions_on_stale_deps / self.decisions_total


def compute_budget(graph: DependencyGraph, root_fact: str) -> int:
    """budget = minimum successful-path cost + recovery allowance.

    Both terms come from the graph itself, not from tuning toward a
    result we wanted to see:
      - minimum successful-path cost is just the number of steps
        required with no invalidation at all (len(graph.steps)).
      - the recovery allowance scales with how much of the graph
        would need to be redone in the worst case (the invalidated
        closure size), plus one step for the replan decision itself.
        This is what keeps the budget fair across topologies of very
        different size -- a flat constant allowance would unfairly
        starve deep or wide graphs of room to recover.
    """
    min_path_cost = len(graph.steps)
    affected = graph.invalidated_closure_size(root_fact)
    recovery_allowance = affected + 1
    return min_path_cost + recovery_allowance


def _recovery_cost(graph: DependencyGraph, root_fact: str) -> int:
    """Cost of redoing the affected portion of the plan, plus the
    replan decision itself. Both executors pay this same cost once
    they decide to replan -- only the timing of that decision differs."""
    return graph.invalidated_closure_size(root_fact) + 1


def run_baseline(graph: DependencyGraph, world: TaskWorld, root_fact: str, budget: int) -> TaskResult:
    order = graph.topological_order()
    steps_used = 0
    pre_failure_work = 0
    replans = 0
    decisions_total = 0
    decisions_on_stale = 0
    completed = False

    for step_id in order:
        world.apply_due_events()
        step = graph.steps[step_id]
        decisions_total += 1
        doomed = world.is_doomed(step)
        if doomed:
            decisions_on_stale += 1

        steps_used += 1
        world.tick = steps_used

        if step.is_action:
            if doomed:
                # Reality reveals itself only now, at execution time.
                replans += 1
                steps_used += _recovery_cost(graph, root_fact)
                world.tick = steps_used
                completed = steps_used <= budget
            else:
                completed = True
            break
        else:
            if doomed:
                pre_failure_work += 1
            if steps_used > budget:
                completed = False
                break

    return TaskResult(
        executor="baseline",
        completed=completed,
        steps_used=steps_used,
        budget=budget,
        replans=replans,
        verifications=0,
        pre_failure_work=pre_failure_work,
        decisions_total=decisions_total,
        decisions_on_stale_deps=decisions_on_stale,
    )


def run_validity_aware(graph: DependencyGraph, world: TaskWorld, root_fact: str, budget: int) -> TaskResult:
    order = graph.topological_order()
    steps_used = 0
    pre_failure_work = 0  # stays 0 by construction: this executor never
                          # knowingly executes a step it believes is invalid
    replans = 0
    verifications = 0
    decisions_total = 0
    decisions_on_stale = 0
    completed = False

    for step_id in order:
        world.apply_due_events()
        step = graph.steps[step_id]
        decisions_total += 1
        if world.is_doomed(step):
            decisions_on_stale += 1

        statuses = [world.facts[f].state for f in step.requires_closure]

        if any(s == ValidityState.SUPERSEDED for s in statuses):
            replans += 1
            steps_used += _recovery_cost(graph, root_fact)
            world.tick = steps_used
            completed = steps_used <= budget
            break

        if any(s in (ValidityState.STALE, ValidityState.UNKNOWN) for s in statuses):
            verifications += 1
            steps_used += 1
            world.tick = steps_used
            ok = world.verify(step.requires_closure)
            if not ok:
                replans += 1
                steps_used += _recovery_cost(graph, root_fact)
                world.tick = steps_used
                completed = steps_used <= budget
                break
            # Verification confirmed the fact is fine -- now actually
            # execute this step (a second step spent: verify, then act).
            steps_used += 1
            world.tick = steps_used
            if step.is_action:
                completed = True
                break
            if steps_used > budget:
                completed = False
                break
            continue

        # ACTIVE: execute normally.
        steps_used += 1
        world.tick = steps_used
        if step.is_action:
            completed = True
            break
        if steps_used > budget:
            completed = False
            break

    return TaskResult(
        executor="validity_aware",
        completed=completed,
        steps_used=steps_used,
        budget=budget,
        replans=replans,
        verifications=verifications,
        pre_failure_work=pre_failure_work,
        decisions_total=decisions_total,
        decisions_on_stale_deps=decisions_on_stale,
    )
