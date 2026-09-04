"""
Fact and validity-state primitives.

A Fact is never deleted when it becomes invalid -- only its `state`
changes, and its prior value/state is pushed onto `history`. Nothing
is forgotten. That is the entire point of the benchmark: the failure
mode under study is not truncation or context loss, it is a stale
fact remaining available as if it were still current.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple


class ValidityState(Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    UNKNOWN = "UNKNOWN"


@dataclass
class Fact:
    id: str
    value: Any
    state: ValidityState = ValidityState.ACTIVE
    valid_until: Optional[int] = None
    history: List[Tuple[int, Any, ValidityState]] = field(default_factory=list)

    def _push_history(self, tick: int) -> None:
        self.history.append((tick, self.value, self.state))

    def replace(self, new_value: Any, tick: int) -> None:
        """Rule 1/2 (explicit replacement / value mutation): the old
        value is superseded by an observed new value."""
        self._push_history(tick)
        self.value = new_value
        self.state = ValidityState.SUPERSEDED

    def mark_ambiguous(self, tick: int) -> None:
        """An observation casts doubt on this fact without confirming
        a specific new value (e.g. 'prices may have changed')."""
        self._push_history(tick)
        self.state = ValidityState.UNKNOWN

    def expire_if_due(self, tick: int) -> None:
        """Rule 5 (temporal expiry): a fact with a validity horizon
        becomes STALE once that horizon passes, with no explicit
        contradiction required."""
        if (
            self.valid_until is not None
            and tick > self.valid_until
            and self.state == ValidityState.ACTIVE
        ):
            self._push_history(tick)
            self.state = ValidityState.STALE

    def confirm(self, tick: int) -> None:
        """Verification found the fact is still current."""
        self._push_history(tick)
        self.state = ValidityState.ACTIVE

    def reject(self, tick: int) -> None:
        """Verification revealed the fact no longer holds."""
        self._push_history(tick)
        self.state = ValidityState.SUPERSEDED
