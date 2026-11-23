from pathlib import Path

import pytest

from automata import HealthState
from domain import Network
from graph import GraphMode, connected_components, isolated_nodes, shortest_path
from loader import (
    ConnectionRecordError,
    DuplicateRecordError,
    EmptyDevicesError,
    MissingEventsError,
    RecordFormatError,
    RecordValidationError,
    ReferenceRecordError,
    SourceEncodingError,
    SourceFileNotFoundError,
    load_network,
)


DEVICES = """\
Router1,192.168.1.1
Switch1,192.168.1.2
Switch2,192.168.1.3
PC1,192.168.1.10
PC2,192.168.1.11
PC3,192.168.1.12
Server1,192.168.1.100
"""
CONNECTIONS = """\
Router1,Switch1
Router1,Switch2
Switch1,Switch2
Switch1,PC1
Switch1,PC2
Switch2,Server1
"""
EVENTS = """\
Router1:RRR
Switch1:RRTT
Switch2:RR
PC1:RR
PC2:R
PC3:R
Server1:RRT
"""


def write_sources(tmp_path, devices=DEVICES, connections=CONNECTIONS, events=EVENTS):
    paths = tuple(tmp_path / name for name in ("devices.txt", "connections.txt", "events.txt"))
    for path, content in zip(paths, (devices, connections, events), strict=True):
        path.write_text(content, encoding="utf-8")
    return paths


def test_load_reference_scenario_and_graph_integration(tmp_path):
    network = load_network(*write_sources(tmp_path))
    assert len(network.devices) == 7
    assert len(network.connections) == 6
    assert network.get_device("Switch1").health is HealthState.FAILURE
    assert network.get_device("Server1").health is HealthState.WARNING
    assert isolated_nodes(network, GraphMode.FISICA) == ("PC3",)
    assert len(connected_components(network, GraphMode.FISICA)) == 2
    assert len(connected_components(network, GraphMode.OPERATIVA)) == 4
    physical = shortest_path(network, "PC1", "Server1", GraphMode.FISICA)
    assert physical is not None and physical.hops == 3
    assert shortest_path(network, "PC1", "Server1", GraphMode.OPERATIVA) is None


def test_committed_data_files_load_reference_scenario():
    root = Path(__file__).resolve().parents[1]
    network = load_network(
        root / "data/devices.txt",
        root / "data/connections.txt",
        root / "data/events.txt",
    )
    assert len(network.devices) == 7
    assert len(network.connections) == 6


def test_missing_file_is_distinguished(tmp_path):
    paths = write_sources(tmp_path)
    with pytest.raises(SourceFileNotFoundError, match="archivo inexistente"):
        load_network(tmp_path / "missing.txt", paths[1], paths[2])


def test_invalid_utf8_is_distinguished(tmp_path):
    paths = write_sources(tmp_path)
    paths[2].write_bytes(b"PC1:\xff")
    with pytest.raises(SourceEncodingError, match="UTF-8 inválida"):
        load_network(*paths)


@pytest.mark.parametrize("devices", ["", "  \n\t\n"])
def test_empty_devices_file(devices, tmp_path):
    with pytest.raises(EmptyDevicesError):
        load_network(*write_sources(tmp_path, devices=devices))


def test_empty_connections_are_allowed(tmp_path):
    network = load_network(*write_sources(tmp_path, connections=""))
    assert len(network.connections) == 0
    assert len(connected_components(network, GraphMode.FISICA)) == 7


def test_blank_lines_and_outer_spaces_are_normalized(tmp_path):
    devices = "\n Router1 , 192.168.1.1 \n\n PC1 , 192.168.1.10 \n"
    connections = " \n Router1 , Router2 \n Router2 , Switch1 \n Switch1 , PC1 \n"
    events = "\n Router1 : R \n Router2 : RR \n Switch1 : R \n PC1 : T \n"
    devices += " Router2 , 192.168.1.2 \n Switch1 , 192.168.1.3 \n"
    network = load_network(*write_sources(tmp_path, devices, connections, events))
    assert len(network.devices) == 4
    assert len(network.connections) == 3


@pytest.mark.parametrize(
    "devices, expected_line",
    [("Router1\n", 1), ("Router1,\n", 1), ("Router1,10.0.0.1,extra\n", 1)],
)
def test_incomplete_or_additional_device_fields(devices, expected_line, tmp_path):
    with pytest.raises(RecordFormatError, match=rf"devices.txt, línea {expected_line}"):
        load_network(*write_sources(tmp_path, devices=devices))


@pytest.mark.parametrize("connections", ["Router1\n", "Router1,Switch1,PC1\n"])
def test_incomplete_or_additional_connection_fields(connections, tmp_path):
    with pytest.raises(RecordFormatError, match=r"connections.txt, línea 1"):
        load_network(*write_sources(tmp_path, connections=connections))


def test_physical_line_number_ignores_blank_records_not_positions(tmp_path):
    devices = "\nRouter1,192.168.1.1\n\nBadId,192.168.1.2\n"
    with pytest.raises(RecordValidationError, match=r"devices.txt, línea 4"):
        load_network(*write_sources(tmp_path, devices=devices))


@pytest.mark.parametrize(
    "devices, message",
    [
        ("Router1,192.168.1.1\nRouter1,192.168.1.2\n", "ID duplicado"),
        ("Router1,192.168.1.1\nRouter2,192.168.1.1\n", "IP duplicada"),
    ],
)
def test_duplicate_device_data(devices, message, tmp_path):
    events = "Router1:R\nRouter2:R\n"
    with pytest.raises(DuplicateRecordError, match=message):
        load_network(*write_sources(tmp_path, devices, "", events))


def test_public_ip_is_rejected_with_context(tmp_path):
    with pytest.raises(RecordValidationError, match=r"devices.txt, línea 1: IP inválida"):
        load_network(*write_sources(tmp_path, devices="Router1,8.8.8.8\n", events="Router1:R\n"))


@pytest.mark.parametrize(
    "devices",
    [
        "ID,IP\n",
        "# Router1,192.168.1.1\n",
        "Router 1,192.168.1.1\n",
    ],
)
def test_headers_comments_and_internal_id_spaces_are_rejected(devices, tmp_path):
    with pytest.raises(RecordValidationError, match=r"devices.txt, línea 1"):
        load_network(*write_sources(tmp_path, devices=devices, connections="", events="Router1:R\n"))


def test_inverse_duplicate_connection(tmp_path):
    connections = CONNECTIONS + "Switch1,Router1\n"
    with pytest.raises(DuplicateRecordError, match=r"connections.txt, línea 7"):
        load_network(*write_sources(tmp_path, connections=connections))


def test_self_connection(tmp_path):
    with pytest.raises(ConnectionRecordError, match="autoconexión no permitida"):
        load_network(*write_sources(tmp_path, connections="Router1,Router1\n"))


def test_incompatible_connection(tmp_path):
    with pytest.raises(ConnectionRecordError, match="enlace incompatible Router1-PC1"):
        load_network(*write_sources(tmp_path, connections="Router1,PC1\n"))


def test_cardinality_exceeded(tmp_path):
    connections = "Switch1,PC1\nSwitch2,PC1\n"
    with pytest.raises(ConnectionRecordError, match=r"connections.txt, línea 2: cardinalidad excedida"):
        load_network(*write_sources(tmp_path, connections=connections))


def test_connection_to_unknown_device(tmp_path):
    with pytest.raises(ReferenceRecordError, match=r"connections.txt, línea 1"):
        load_network(*write_sources(tmp_path, connections="Router1,Switch9\n"))


def test_events_for_unknown_device(tmp_path):
    with pytest.raises(ReferenceRecordError, match=r"events.txt, línea 8"):
        load_network(*write_sources(tmp_path, events=EVENTS + "PC9:R\n"))


def test_device_without_events(tmp_path):
    with pytest.raises(MissingEventsError, match="PC3"):
        load_network(*write_sources(tmp_path, events=EVENTS.replace("PC3:R\n", "")))


def test_repeated_events_preserve_order_and_state(tmp_path):
    devices = "Switch1,192.168.1.2\nPC1,192.168.1.10\n"
    events = "Switch1:R\nPC1:RR\nSwitch1:TT\n"
    network = load_network(*write_sources(tmp_path, devices, "Switch1,PC1\n", events))
    assert network.get_device("Switch1").health is HealthState.FAILURE
    assert network.get_device("PC1").health is HealthState.NORMAL


@pytest.mark.parametrize("events", ["PC1:\n", "PC1:RX\n", "PC1:R:T\n"])
def test_invalid_event_records(events, tmp_path):
    devices = "PC1,192.168.1.10\n"
    error = RecordFormatError if events == "PC1:\n" or events == "PC1:R:T\n" else RecordValidationError
    with pytest.raises(error, match=r"events.txt, línea 1"):
        load_network(*write_sources(tmp_path, devices, "", events))


def test_failed_load_does_not_modify_existing_network(tmp_path):
    existing = Network()
    existing.register_device("Router9", "10.0.0.9", "R")
    before = (existing.devices, existing.adjacency, existing.connections)

    with pytest.raises(RecordValidationError):
        load_network(*write_sources(tmp_path, devices="Router1,8.8.8.8\n", events="Router1:R\n"))

    assert (existing.devices, existing.adjacency, existing.connections) == before
