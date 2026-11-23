import pytest

from core.automata import HealthState, process_health


@pytest.mark.parametrize(
    "events, expected",
    [
        ("RRR", HealthState.NORMAL),
        ("RRT", HealthState.WARNING),
        ("RRTT", HealthState.FAILURE),
        ("RRTTR", HealthState.NORMAL),
    ],
)
def test_sequences_from_initial_state(events, expected):
    assert process_health(HealthState.NORMAL, events) is expected


def test_state_persists_between_sequences():
    state = process_health(HealthState.NORMAL, "RRT")
    assert process_health(state, "T") is HealthState.FAILURE


def test_failure_recovers_with_response():
    assert process_health(HealthState.FAILURE, "R") is HealthState.NORMAL


def test_failure_persists_with_timeout():
    assert process_health(HealthState.FAILURE, "T") is HealthState.FAILURE


def test_invalid_sequence_does_not_mutate_prior_state():
    state = HealthState.WARNING
    with pytest.raises(ValueError):
        process_health(state, "TX")
    assert state is HealthState.WARNING
