from types import MappingProxyType

import pytest

from automata import HealthState
from domain import (
    CardinalityError,
    Connection,
    ConnectionNotFoundError,
    Device,
    DuplicateError,
    IncompatibleConnectionError,
    Network,
)


def populated_network():
    network = Network()
    network.register_device("Router1", "10.0.0.1", "R")
    network.register_device("Switch1", "10.0.0.2", "R")
    network.register_device("Switch2", "10.0.0.3", "R")
    network.register_device("PC1", "10.0.0.4", "R")
    network.register_device("Server1", "10.0.0.5", "R")
    return network


def assert_symmetric(network):
    for device_id, neighbors in network.adjacency.items():
        for neighbor in neighbors:
            assert device_id in network.adjacency[neighbor]


def test_device_derives_read_only_state():
    device = Device("PC1", "192.168.1.2", "T")
    assert device.type == "PC"
    assert device.health is HealthState.WARNING
    assert device.operational
    for attribute, value in (("id", "PC2"), ("type", "Router"), ("ip", "10.0.0.1"), ("health", HealthState.FAILURE)):
        with pytest.raises(AttributeError):
            setattr(device, attribute, value)


@pytest.mark.parametrize("events", ["", "RX"])
def test_device_requires_valid_initial_events(events):
    with pytest.raises(ValueError):
        Device("PC1", "192.168.1.2", events)


def test_connection_is_undirected_and_canonical():
    assert Connection("Switch1", "PC1") == Connection("PC1", "Switch1")
    assert len({Connection("Switch1", "PC1"), Connection("PC1", "Switch1")}) == 1


def test_register_device_and_reject_duplicates():
    network = Network()
    device = network.register_device("Router1", "10.0.0.1", "R")
    assert network.get_device("Router1") is device
    with pytest.raises(DuplicateError):
        network.register_device("Router1", "10.0.0.2", "R")
    with pytest.raises(DuplicateError):
        network.register_device("Router2", "10.0.0.1", "R")
    assert set(network.devices) == {"Router1"}


def test_change_ip_preserves_other_state_and_connections():
    network = populated_network()
    network.connect("Router1", "Switch1")
    device = network.get_device("Router1")
    old_health = device.health
    old_connections = network.connections
    network.change_ip("Router1", "172.16.0.8")
    assert device.ip == "172.16.0.8"
    assert device.id == "Router1"
    assert device.health is old_health
    assert network.connections == old_connections


def test_reject_same_or_invalid_ip_atomically():
    network = populated_network()
    with pytest.raises(DuplicateError):
        network.change_ip("Router1", "10.0.0.1")
    with pytest.raises(ValueError):
        network.change_ip("Router1", "8.8.8.8")
    assert network.get_device("Router1").ip == "10.0.0.1"


def test_create_allowed_connections_and_preserve_symmetry():
    network = populated_network()
    expected = {
        Connection("Router1", "Switch1"),
        Connection("Switch1", "Switch2"),
        Connection("Switch1", "PC1"),
        Connection("Switch2", "Server1"),
    }
    for connection in expected:
        network.connect(connection.first, connection.second)
        assert_symmetric(network)
    assert network.connections == expected


def test_reject_incompatible_self_and_inverse_duplicate():
    network = populated_network()
    with pytest.raises(IncompatibleConnectionError):
        network.connect("Router1", "PC1")
    with pytest.raises(ValueError):
        network.connect("Router1", "Router1")
    network.connect("Router1", "Switch1")
    with pytest.raises(DuplicateError):
        network.connect("Switch1", "Router1")
    assert_symmetric(network)


@pytest.mark.parametrize("limited_id", ["PC1", "Server1"])
def test_pc_and_server_accept_only_one_connection(limited_id):
    network = populated_network()
    network.connect("Switch1", limited_id)
    before = network.adjacency
    with pytest.raises(CardinalityError):
        network.connect("Switch2", limited_id)
    assert network.adjacency == before
    assert_symmetric(network)


def test_disconnect_existing_and_reject_missing_connection():
    network = populated_network()
    network.connect("Router1", "Switch1")
    network.disconnect("Switch1", "Router1")
    assert not network.connections
    assert_symmetric(network)
    with pytest.raises(ConnectionNotFoundError):
        network.disconnect("Router1", "Switch1")


def test_health_failure_keeps_physical_links():
    network = populated_network()
    network.connect("Switch1", "PC1")
    before = network.connections
    assert network.register_health("PC1", "TT") is HealthState.FAILURE
    assert not network.get_device("PC1").operational
    assert network.connections == before


def test_invalid_health_sequence_is_atomic():
    network = populated_network()
    before = network.get_device("PC1").health
    with pytest.raises(ValueError):
        network.register_health("PC1", "TX")
    assert network.get_device("PC1").health is before


def test_internal_collections_cannot_be_mutated_externally():
    network = populated_network()
    assert isinstance(network.devices, MappingProxyType)
    with pytest.raises(TypeError):
        network.devices["PC2"] = network.get_device("PC1")
    with pytest.raises(AttributeError):
        network.adjacency["PC1"].add("Switch1")
    assert network.neighbors("PC1") == frozenset()
