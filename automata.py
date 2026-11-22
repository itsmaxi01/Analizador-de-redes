"""Deterministic health automaton for network devices."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping

from validators import validate_health_events


class HealthState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    FAILURE = "FAILURE"

    @property
    def operational(self) -> bool:
        return self is not HealthState.FAILURE


_TRANSITION_ROWS: dict[HealthState, Mapping[str, HealthState]] = {
    HealthState.NORMAL: MappingProxyType(
        {"R": HealthState.NORMAL, "T": HealthState.WARNING}
    ),
    HealthState.WARNING: MappingProxyType(
        {"R": HealthState.NORMAL, "T": HealthState.FAILURE}
    ),
    HealthState.FAILURE: MappingProxyType(
        {"R": HealthState.NORMAL, "T": HealthState.FAILURE}
    ),
}
TRANSITIONS: Mapping[HealthState, Mapping[str, HealthState]] = MappingProxyType(
    _TRANSITION_ROWS
)


def process_health(current_state: HealthState, events: str) -> HealthState:
    """Process a valid event sequence without mutating the supplied state."""
    if not isinstance(current_state, HealthState):
        raise TypeError("current_state must be a HealthState value.")
    validated_events = validate_health_events(events)

    state = current_state
    for event in validated_events:
        state = TRANSITIONS[state][event]
    return state
