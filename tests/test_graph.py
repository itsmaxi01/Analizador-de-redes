import pytest

from automata import HealthState
from domain import DeviceNotFoundError, Network
from graph import (
    GraphMode,
    Route,
    connected_components,
    degree,
    is_connected,
    isolated_nodes,
    shortest_path,
)


def integration_network() -> Network:
    network = Network()
    for device_id, ip, events in (
        ("Router1", "192.168.1.1", "RRR"),
        ("Switch1", "192.168.1.2", "RRTT"),
        ("Switch2", "192.168.1.3", "RR"),
        ("PC1", "192.168.1.10", "RR"),
        ("PC2", "192.168.1.11", "R"),
        ("PC3", "192.168.1.12", "R"),
        ("Server1", "192.168.1.100", "RRT"),
    ):
        network.register_device(device_id, ip, events)

    for first, second in (
        ("Router1", "Switch1"),
        ("Router1", "Switch2"),
        ("Switch1", "Switch2"),
        ("Switch1", "PC1"),
        ("Switch1", "PC2"),
        ("Switch2", "Server1"),
    ):
        network.connect(first, second)
    return network


def network_snapshot(network: Network):
    return (
        tuple(
            (device_id, device.ip, device.health)
            for device_id, device in sorted(network.devices.items())
        ),
        network.adjacency,
        network.connections,
    )


def test_route_derives_hops_and_rejects_empty_path():
    route = Route(("Router1", "Switch1", "PC1"))
    assert route.hops == 2
    with pytest.raises(ValueError):
        Route(())


def test_required_integration_results_and_physical_route():
    network = integration_network()
    assert network.get_device("Switch1").health is HealthState.FAILURE
    assert network.get_device("Server1").health is HealthState.WARNING
    assert degree(network, "Switch1", GraphMode.FISICA) == 4
    assert isolated_nodes(network, GraphMode.FISICA) == ("PC3",)
    assert len(connected_components(network, GraphMode.FISICA)) == 2
    assert len(connected_components(network, GraphMode.OPERATIVA)) == 4
    route = shortest_path(network, "PC1", "Server1", GraphMode.FISICA)
    assert route == Route(("PC1", "Switch1", "Switch2", "Server1"))
    assert route.hops == 3
    assert shortest_path(network, "PC1", "Server1", GraphMode.OPERATIVA) is None


def test_recovery_restores_operational_route_without_changing_links():
    network = integration_network()
    before = network.connections
    network.register_health("Switch1", "R")
    route = shortest_path(network, "PC1", "Server1", GraphMode.OPERATIVA)
    assert route == Route(("PC1", "Switch1", "Switch2", "Server1"))
    assert route.hops == 3
    assert network.connections == before


@pytest.mark.parametrize("mode", list(GraphMode))
def test_origin_equals_destination(mode):
    network = integration_network()
    assert shortest_path(network, "PC1", "PC1", mode) == Route(("PC1",))


def test_failed_device_has_no_operational_zero_hop_route():
    network = integration_network()
    assert shortest_path(network, "Switch1", "Switch1", GraphMode.FISICA) == Route(
        ("Switch1",)
    )
    assert shortest_path(network, "Switch1", "Switch1", GraphMode.OPERATIVA) is None


@pytest.mark.parametrize("function", [shortest_path, is_connected])
def test_unknown_endpoints_raise(function):
    network = integration_network()
    with pytest.raises(DeviceNotFoundError):
        function(network, "Router9", "PC1", GraphMode.FISICA)
    with pytest.raises(DeviceNotFoundError):
        function(network, "PC1", "Server9", GraphMode.FISICA)


def test_unknown_mode_is_rejected():
    network = integration_network()
    with pytest.raises(ValueError):
        shortest_path(network, "PC1", "Server1", "FISICA")


def test_failed_endpoints_are_excluded_from_operational_graph():
    network = integration_network()
    assert not is_connected(network, "Switch1", "Router1", GraphMode.OPERATIVA)
    assert degree(network, "Switch1", GraphMode.OPERATIVA) is None
    assert "Switch1" not in isolated_nodes(network, GraphMode.OPERATIVA)
    assert all(
        "Switch1" not in component
        for component in connected_components(network, GraphMode.OPERATIVA)
    )


def test_failed_intermediate_is_ignored_and_alternative_is_found():
    network = Network()
    for device_id, ip, events in (
        ("Router1", "10.0.0.1", "R"),
        ("Router2", "10.0.0.2", "R"),
        ("Router3", "10.0.0.3", "TT"),
        ("Router4", "10.0.0.4", "R"),
    ):
        network.register_device(device_id, ip, events)
    for first, second in (
        ("Router1", "Router2"),
        ("Router2", "Router4"),
        ("Router1", "Router3"),
        ("Router3", "Router4"),
    ):
        network.connect(first, second)

    assert shortest_path(network, "Router1", "Router4", GraphMode.FISICA) == Route(
        ("Router1", "Router2", "Router4")
    )
    assert shortest_path(network, "Router1", "Router4", GraphMode.OPERATIVA) == Route(
        ("Router1", "Router2", "Router4")
    )


def test_neighbor_sorting_makes_equal_routes_deterministic():
    network = Network()
    for number in range(1, 5):
        network.register_device(f"Router{number}", f"10.0.0.{number}", "R")
    network.connect("Router1", "Router3")
    network.connect("Router3", "Router4")
    network.connect("Router1", "Router2")
    network.connect("Router2", "Router4")
    assert shortest_path(network, "Router1", "Router4", GraphMode.FISICA) == Route(
        ("Router1", "Router2", "Router4")
    )


def test_cycles_and_disconnected_network_terminate_correctly():
    network = integration_network()
    components = connected_components(network, GraphMode.FISICA)
    assert components == (
        ("PC1", "PC2", "Router1", "Server1", "Switch1", "Switch2"),
        ("PC3",),
    )
    assert not is_connected(network, "PC3", "Router1", GraphMode.FISICA)


def test_empty_network_and_network_without_connections():
    empty = Network()
    assert isolated_nodes(empty, GraphMode.FISICA) == ()
    assert connected_components(empty, GraphMode.OPERATIVA) == ()

    network = Network()
    network.register_device("Router1", "10.0.0.1", "R")
    network.register_device("Switch1", "10.0.0.2", "TT")
    assert isolated_nodes(network, GraphMode.FISICA) == ("Router1", "Switch1")
    assert isolated_nodes(network, GraphMode.OPERATIVA) == ("Router1",)
    assert connected_components(network, GraphMode.FISICA) == (
        ("Router1",),
        ("Switch1",),
    )
    assert connected_components(network, GraphMode.OPERATIVA) == (("Router1",),)


def test_queries_follow_later_connection_changes():
    network = Network()
    network.register_device("Router1", "10.0.0.1", "R")
    network.register_device("Switch1", "10.0.0.2", "R")
    assert not is_connected(network, "Router1", "Switch1", GraphMode.FISICA)
    network.connect("Router1", "Switch1")
    assert is_connected(network, "Router1", "Switch1", GraphMode.FISICA)
    network.disconnect("Router1", "Switch1")
    assert not is_connected(network, "Router1", "Switch1", GraphMode.FISICA)


def test_ip_changes_do_not_change_connectivity():
    network = integration_network()
    before = shortest_path(network, "Router1", "Server1", GraphMode.OPERATIVA)
    network.change_ip("Router1", "172.16.0.1")
    assert shortest_path(network, "Router1", "Server1", GraphMode.OPERATIVA) == before


def test_repeated_queries_do_not_mutate_network():
    network = integration_network()
    before = network_snapshot(network)
    for _ in range(3):
        shortest_path(network, "PC1", "Server1", GraphMode.FISICA)
        is_connected(network, "PC1", "Server1", GraphMode.OPERATIVA)
        degree(network, "Switch1", GraphMode.FISICA)
        isolated_nodes(network, GraphMode.OPERATIVA)
        connected_components(network, GraphMode.FISICA)
    assert network_snapshot(network) == before


def test_operational_device_with_only_failed_neighbors_is_isolated():
    network = integration_network()
    assert degree(network, "PC1", GraphMode.FISICA) == 1
    assert degree(network, "PC1", GraphMode.OPERATIVA) == 0
    assert "PC1" in isolated_nodes(network, GraphMode.OPERATIVA)


def test_recovering_intermediate_updates_components_immediately():
    network = integration_network()
    assert len(connected_components(network, GraphMode.OPERATIVA)) == 4
    network.register_health("Switch1", "R")
    assert len(connected_components(network, GraphMode.OPERATIVA)) == 2
    assert is_connected(network, "PC1", "Server1", GraphMode.OPERATIVA)
