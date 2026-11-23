from pathlib import Path

import pytest

from automata import HealthState
from domain import CardinalityError, DeviceNotFoundError, DuplicateError
from graph import (
    GraphMode,
    connected_components,
    degree,
    is_connected,
    isolated_nodes,
    shortest_path,
)
from session import NetworkSession


def write_scenario(tmp_path: Path) -> tuple[Path, Path, Path]:
    contents = (
        """\
Router1,192.168.1.1
Switch1,192.168.1.2
Switch2,192.168.1.3
PC1,192.168.1.10
Server1,192.168.1.100
""",
        """\
Router1,Switch1
Router1,Switch2
Switch1,PC1
Switch2,Server1
""",
        """\
Router1:R
Switch1:RRTT
Switch2:R
PC1:R
Server1:RRT
""",
    )
    paths = tuple(
        tmp_path / filename
        for filename in ("devices.txt", "connections.txt", "events.txt")
    )
    for path, content in zip(paths, contents, strict=True):
        path.write_text(content, encoding="utf-8")
    return paths


def public_snapshot(network):
    return (
        tuple(
            (device_id, device.type, device.ip, device.health)
            for device_id, device in sorted(network.devices.items())
        ),
        network.adjacency,
        network.connections,
    )


def route_hops(network, mode):
    route = shortest_path(network, "PC1", "Server1", mode)
    return None if route is None else route.hops


def test_sequences_a_to_e_reflect_current_network_immediately(tmp_path):
    session = NetworkSession()
    network = session.load(*write_scenario(tmp_path))

    # A: initial failure fragments only the operational graph.
    assert network.get_device("Switch1").health is HealthState.FAILURE
    assert network.get_device("Server1").health is HealthState.WARNING
    assert network.get_device("Server1").operational
    assert route_hops(network, GraphMode.FISICA) == 4
    assert route_hops(network, GraphMode.OPERATIVA) is None

    # Repeated reads are pure and independent from prior results.
    initial = public_snapshot(network)
    assert route_hops(network, GraphMode.FISICA) == 4
    assert connected_components(network, GraphMode.FISICA) == (
        ("PC1", "Router1", "Server1", "Switch1", "Switch2"),
    )
    assert public_snapshot(network) == initial

    # B: recovery re-enables the existing physical path.
    physical_connections = network.connections
    network.register_health("Switch1", "R")
    assert network.get_device("Switch1").health is HealthState.NORMAL
    assert route_hops(network, GraphMode.OPERATIVA) == 4
    assert network.connections == physical_connections

    # C: state persists between instructions and physical links remain.
    network.register_health("Switch1", "T")
    assert network.get_device("Switch1").health is HealthState.WARNING
    network.register_health("Switch1", "T")
    assert network.get_device("Switch1").health is HealthState.FAILURE
    assert route_hops(network, GraphMode.OPERATIVA) is None
    assert network.connections == physical_connections

    # D: topology changes bypass the failed switch without changing health.
    pc_health = network.get_device("PC1").health
    network.disconnect("PC1", "Switch1")
    assert not is_connected(network, "PC1", "Server1", GraphMode.FISICA)
    network.connect("PC1", "Switch2")
    assert route_hops(network, GraphMode.OPERATIVA) == 2
    assert network.get_device("Switch1").health is HealthState.FAILURE
    assert network.neighbors("Switch1") == frozenset({"Router1"})
    assert network.get_device("PC1").health is pc_health

    # E: administrative addressing does not affect graph results.
    degrees_before = {
        device_id: degree(network, device_id, GraphMode.FISICA)
        for device_id in network.devices
    }
    components_before = connected_components(network, GraphMode.OPERATIVA)
    network.change_ip("PC1", "172.16.0.10")
    assert network.get_device("PC1").ip == "172.16.0.10"
    assert route_hops(network, GraphMode.OPERATIVA) == 2
    assert {
        device_id: degree(network, device_id, GraphMode.FISICA)
        for device_id in network.devices
    } == degrees_before
    assert connected_components(network, GraphMode.OPERATIVA) == components_before
    assert network.get_device("PC1").health is pc_health


def test_sequence_f_invalid_operations_are_atomic(tmp_path):
    network = NetworkSession().load(*write_scenario(tmp_path))
    network.disconnect("PC1", "Switch1")
    network.connect("PC1", "Switch2")
    network.change_ip("PC1", "172.16.0.10")

    operations = (
        (CardinalityError, lambda: network.connect("Switch1", "PC1")),
        (DuplicateError, lambda: network.connect("Switch2", "PC1")),
        (ValueError, lambda: network.connect("Router1", "Router1")),
        (DuplicateError, lambda: network.change_ip("PC1", "192.168.1.1")),
        (DuplicateError, lambda: network.change_ip("PC1", "172.16.0.10")),
        (ValueError, lambda: network.register_health("PC1", "RX")),
        (DeviceNotFoundError, lambda: network.change_ip("PC9", "10.0.0.9")),
    )

    for error, operation in operations:
        before = public_snapshot(network)
        with pytest.raises(error):
            operation()
        assert public_snapshot(network) == before


def test_new_isolated_device_keeps_health_and_forms_component(tmp_path):
    network = NetworkSession().load(*write_scenario(tmp_path))
    device = network.register_device("PC2", "192.168.1.11", "T")
    assert device.health is HealthState.WARNING
    assert network.neighbors("PC2") == frozenset()
    assert "PC2" in isolated_nodes(network, GraphMode.FISICA)
    assert ("PC2",) in connected_components(network, GraphMode.OPERATIVA)


def test_disconnect_does_not_change_health_and_reconnect_updates_routes(tmp_path):
    network = NetworkSession().load(*write_scenario(tmp_path))
    network.register_health("Switch1", "R")
    health_before = network.get_device("PC1").health
    assert route_hops(network, GraphMode.OPERATIVA) == 4
    network.disconnect("PC1", "Switch1")
    assert route_hops(network, GraphMode.OPERATIVA) is None
    assert network.get_device("PC1").health is health_before
    network.connect("PC1", "Switch2")
    assert route_hops(network, GraphMode.OPERATIVA) == 2
