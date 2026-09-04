"""
TaskWorld holds the live Facts for one benchmark run and the scheduled
events that change them.

Deliberate design point: `ground_truth_broken` (what the world has
actually done) is tracked separately from `Fact.state` (what an
executor currently believes). Neither executor is allowed to read
`ground_truth_broken` directly -- it is only consulted by the world
itself, at the two moments where reality is allowed to reveal itself:
when an Action actually executes, or when a Verify step is spent.
Everything else the executors do is driven purely by belief (state).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .facts import Fact, ValidityState


@dataclass
class InvalidationEvent:
    tick: int
    fact_id: str
    kind: str  # "replace" | "ambiguous"
    new_value: object = None
    ground_truth_changed: Optional[bool] = None  # only used for kind == "ambiguous"


class TaskWorld:
    def __init__(self, facts: Dict[str, Fact], events: List[InvalidationEvent]):
        self.facts = facts
        self.events = sorted(events, key=lambda e: e.tick)
        self.tick = 0
        self.ground_truth_broken: Dict[str, bool] = {}
        self._ambiguous_truth: Dict[str, bool] = {}

    def apply_due_events(self) -> None:
        while self.events and self.events[0].tick <= self.tick:
            event = self.events.pop(0)
            fact = self.facts[event.fact_id]
            if event.kind == "replace":
                fact.replace(event.new_value, self.tick)
                self.ground_truth_broken[event.fact_id] = True
            elif event.kind == "ambiguous":
                fact.mark_ambiguous(self.tick)
                self.ground_truth_broken[event.fact_id] = bool(event.ground_truth_changed)
                self._ambiguous_truth[event.fact_id] = bool(event.ground_truth_changed)
            else:
                raise ValueError(f"Unknown event kind: {event.kind}")
        for fact in self.facts.values():
            fact.expire_if_due(self.tick)

    def is_doomed(self, step) -> bool:
        """Ground-truth check: would this step's real-world
        precondition currently fail? Used to (a) determine whether an
        Action actually fails when executed, and (b) measure, purely
        for reporting, whether a given decision was structurally
        exposed to invalidated reality (the SCUR/PFW bookkeeping)."""
        return any(self.ground_truth_broken.get(f, False) for f in step.requires_closure)

    def verify(self, fact_ids) -> bool:
        """Spend a verification: resolve ground truth for any
        ambiguous fact in `fact_ids`. Returns True if everything
        checked out (still fine), False if verification reveals a
        real change."""
        ok = True
        for f in fact_ids:
            fact = self.facts[f]
            if fact.state in (ValidityState.STALE, ValidityState.UNKNOWN):
                changed = self._ambiguous_truth.get(f, False)
                if changed:
                    fact.reject(self.tick)
                    ok = False
                else:
                    fact.confirm(self.tick)
        return ok
