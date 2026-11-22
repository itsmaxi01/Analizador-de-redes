import pytest

from validators import (
    are_types_compatible,
    infer_device_type,
    validate_device_id,
    validate_health_events,
    validate_ipv4,
)


@pytest.mark.parametrize(
    "device_id, expected_type",
    [("Router1", "Router"), ("Switch20", "Switch"), ("PC3", "PC"), ("Server9", "Server")],
)
def test_valid_ids_and_inferred_types(device_id, expected_type):
    assert validate_device_id(device_id) == device_id
    assert infer_device_type(device_id) == expected_type


@pytest.mark.parametrize(
    "device_id",
    ["", "router1", "Router0", "Router01", "Router-1", "PC1x", "Laptop1", 1],
)
def test_invalid_ids(device_id):
    with pytest.raises(ValueError):
        validate_device_id(device_id)


@pytest.mark.parametrize("ip", ["10.0.0.1", "172.16.0.254", "172.31.255.1", "192.168.10.20"])
def test_valid_private_ipv4(ip):
    assert validate_ipv4(ip) == ip


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",
        "172.15.0.1",
        "172.32.0.1",
        "10.0.0.0",
        "10.0.0.255",
        "10.01.0.1",
        "10.0.0.256",
        "10.0.0",
    ],
)
def test_invalid_ipv4(ip):
    with pytest.raises(ValueError):
        validate_ipv4(ip)


@pytest.mark.parametrize("events", ["", "r", "RT X", "RX", None])
def test_invalid_health_events(events):
    with pytest.raises(ValueError):
        validate_health_events(events)


@pytest.mark.parametrize(
    "first, second",
    [("Router", "Router"), ("Router", "Switch"), ("Switch", "Switch"), ("Switch", "PC"), ("Switch", "Server")],
)
def test_allowed_type_pairs(first, second):
    assert are_types_compatible(first, second)
    assert are_types_compatible(second, first)


def test_disallowed_type_pair():
    assert not are_types_compatible("Router", "PC")
