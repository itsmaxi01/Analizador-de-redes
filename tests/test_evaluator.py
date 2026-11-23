from pathlib import Path

import pytest

from core.automata import HealthState
from core.domain import (
    CardinalityError,
    ConnectionNotFoundError,
    DeviceNotFoundError,
    DuplicateError,
    IncompatibleConnectionError,
)
from language.evaluator import (
    DeviceView,
    Diagnosis,
    HealthView,
    LoadSummary,
    SemanticError,
    Visualization,
    evaluate,
)
from core.graph import Route
from core.loader import RecordValidationError
from core.session import NetworkSession, NoNetworkLoadedError


def write_data(
    root: Path,
    devices: str,
    connections: str,
    events: str,
    name: str = "network",
) -> Path:
    directory = root / name
    directory.mkdir()
    for filename, content in (
        ("devices.txt", devices),
        ("connections.txt", connections),
        ("events.txt", events),
    ):
        (directory / filename).write_text(content, encoding="utf-8")
    return directory


def base_data(tmp_path: Path, name: str = "base") -> Path:
    return write_data(
        tmp_path,
        "Router1,10.0.0.1\nSwitch1,10.0.0.2\nPC1,10.0.0.3\nServer1,10.0.0.4\n",
        "Router1,Switch1\nSwitch1,PC1\nSwitch1,Server1\n",
        "Router1:R\nSwitch1:R\nPC1:R\nServer1:R\n",
        name,
    )


def loaded_session(tmp_path: Path) -> NetworkSession:
    session = NetworkSession()
    evaluate(("CARGAR",), session, data_dir=base_data(tmp_path))
    return session


def snapshot(session: NetworkSession):
    network = session.require_network()
    return (
        tuple(
            (key, value.ip, value.health)
            for key, value in sorted(network.devices.items())
        ),
        network.adjacency,
        network.connections,
    )


def test_cargar_initial_replaces_and_invalid_load_is_atomic(tmp_path):
    session = NetworkSession()
    first_dir = base_data(tmp_path, "first")
    assert evaluate(("CARGAR",), session, data_dir=first_dir) == LoadSummary(4, 3)
    first = session.require_network()

    second_dir = write_data(
        tmp_path,
        "Switch2,192.168.1.2\nPC2,192.168.1.3\n",
        "Switch2,PC2\n",
        "Switch2:T\nPC2:R\n",
        "second",
    )
    assert evaluate(("CARGAR",), session, data_dir=second_dir) == LoadSummary(2, 1)
    assert session.require_network() is not first
    assert set(session.require_network().devices) == {"Switch2", "PC2"}

    current = session.require_network()
    bad_dir = write_data(
        tmp_path, "Router2,8.8.8.8\n", "", "Router2:R\n", "bad"
    )
    with pytest.raises(RecordValidationError):
        evaluate(("CARGAR",), session, data_dir=bad_dir)
    assert session.require_network() is current


def test_cargar_default_directory_is_project_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    session = NetworkSession()
    assert evaluate(("CARGAR",), session) == LoadSummary(7, 6)


def test_operation_without_loaded_network():
    with pytest.raises(NoNetworkLoadedError):
        evaluate(("DISPOSITIVOS",), NetworkSession())


def test_register_valid_duplicate_and_public_ip(tmp_path):
    session = loaded_session(tmp_path)
    result = evaluate(("REGISTRAR", "PC2", "10.0.0.5", "T"), session)
    assert result == DeviceView("PC2", "PC", "10.0.0.5", HealthState.WARNING, True)
    assert session.require_network().neighbors("PC2") == frozenset()
    before = snapshot(session)
    with pytest.raises(DuplicateError):
        evaluate(("REGISTRAR", "PC2", "10.0.0.6", "R"), session)
    with pytest.raises(ValueError):
        evaluate(("REGISTRAR", "PC3", "8.8.8.8", "R"), session)
    assert snapshot(session) == before


def test_change_ip_preserves_route_health_and_rejects_same_ip(tmp_path):
    session = loaded_session(tmp_path)
    before_route = evaluate(("CAMINO", "PC1", "Router1", "FISICA"), session)
    before_health = evaluate(("SALUD", "PC1"), session)
    changed = evaluate(("CAMBIAR_IP", "PC1", "172.16.0.10"), session)
    assert changed.ip == "172.16.0.10"
    assert evaluate(("CAMINO", "PC1", "Router1", "FISICA"), session) == before_route
    assert evaluate(("SALUD", "PC1"), session) == before_health
    with pytest.raises(DuplicateError):
        evaluate(("CAMBIAR_IP", "PC1", "172.16.0.10"), session)


def test_connect_disconnect_and_domain_failures_are_atomic(tmp_path):
    session = loaded_session(tmp_path)
    evaluate(("REGISTRAR", "Switch2", "10.0.0.5", "TT"), session)
    link = evaluate(("CONECTAR", "Router1", "Switch2"), session)
    assert link.endpoints == frozenset({"Router1", "Switch2"})
    assert not session.require_network().get_device("Switch2").operational
    assert evaluate(("DESCONECTAR", "Switch2", "Router1"), session) == link
    with pytest.raises(ConnectionNotFoundError):
        evaluate(("DESCONECTAR", "Switch2", "Router1"), session)

    before = snapshot(session)
    with pytest.raises(IncompatibleConnectionError):
        evaluate(("CONECTAR", "PC1", "Server1"), session)
    evaluate(("REGISTRAR", "Switch3", "10.0.0.6", "R"), session)
    with pytest.raises(CardinalityError):
        evaluate(("CONECTAR", "Switch3", "PC1"), session)
    assert session.require_network().neighbors("PC1") == frozenset({"Switch1"})
    assert before[1]["PC1"] == session.require_network().adjacency["PC1"]


def test_event_warning_failure_recovery_and_connection_persistence(tmp_path):
    session = loaded_session(tmp_path)
    assert evaluate(("EVENTO", "PC1", "T"), session) == HealthView(
        "PC1", HealthState.WARNING, True
    )
    assert evaluate(("EVENTO", "PC1", "T"), session).health is HealthState.FAILURE
    assert session.require_network().neighbors("PC1") == frozenset({"Switch1"})
    assert evaluate(("EVENTO", "PC1", "R"), session).health is HealthState.NORMAL


def test_health_state_and_boolean_queries_cover_all_states(tmp_path):
    session = loaded_session(tmp_path)
    evaluate(("EVENTO", "Switch1", "T"), session)
    evaluate(("EVENTO", "Server1", "TT"), session)
    assert evaluate(("OPERATIVO", "Router1"), session) is True
    assert evaluate(("OPERATIVO", "Switch1"), session) is True
    assert evaluate(("OPERATIVO", "Server1"), session) is False
    assert evaluate(("ES_ESTADO", "Router1", "NORMAL"), session) is True
    assert evaluate(("ES_ESTADO", "Switch1", "WARNING"), session) is True
    assert evaluate(("ES_ESTADO", "Server1", "FAILURE"), session) is True
    assert evaluate(("ES_ESTADO", "Switch1", "NORMAL"), session) is False


def test_routes_paths_degrees_isolation_components_and_states(tmp_path):
    session = loaded_session(tmp_path)
    evaluate(("REGISTRAR", "PC2", "10.0.0.5", "TT"), session)
    evaluate(("EVENTO", "Switch1", "TT"), session)
    assert evaluate(("RUTA", "PC1", "Router1", "FISICA"), session) is True
    assert evaluate(("RUTA", "PC1", "Router1", "OPERATIVA"), session) is False
    path = evaluate(("CAMINO", "PC1", "Router1", "FISICA"), session)
    assert path == Route(("PC1", "Switch1", "Router1")) and path.hops == 2
    assert evaluate(("CAMINO", "PC1", "Router1", "OPERATIVA"), session) is None
    assert evaluate(("GRADO", "Switch1", "OPERATIVA"), session) is None
    assert evaluate(("AISLADOS", "OPERATIVA"), session) == (
        "PC1", "Router1", "Server1"
    )
    assert evaluate(("COMPONENTES", "FISICA"), session) == (
        ("PC1", "Router1", "Server1", "Switch1"),
        ("PC2",),
    )
    assert evaluate(("COMPONENTES", "OPERATIVA"), session) == (
        ("PC1",),
        ("Router1",),
        ("Server1",),
    )
    assert evaluate(("ESTADOS", "FAILURE"), session) == ("PC2", "Switch1")


def test_inventory_connections_and_visualization_are_deterministic_and_immutable(tmp_path):
    session = loaded_session(tmp_path)
    before = snapshot(session)
    devices = evaluate(("DISPOSITIVOS",), session)
    connections = evaluate(("CONEXIONES",), session)
    visualization = evaluate(("VISUALIZAR",), session)
    assert tuple(item.device_id for item in devices) == (
        "PC1", "Router1", "Server1", "Switch1"
    )
    assert tuple((item.first, item.second) for item in connections) == (
        ("PC1", "Switch1"),
        ("Router1", "Switch1"),
        ("Server1", "Switch1"),
    )
    assert visualization == Visualization(devices, connections)
    assert snapshot(session) == before


def test_nested_boolean_prevalidation_happens_before_short_circuit(tmp_path):
    session = loaded_session(tmp_path)
    ast = (
        "Y",
        ("OPERATIVO", "PC1"),
        ("O", ("RUTA", "PC1", "Server1", "FISICA"), ("ES_ESTADO", "Switch1", "WARNING")),
    )
    assert evaluate(ast, session) is True
    with pytest.raises(DeviceNotFoundError):
        evaluate(("O", ("OPERATIVO", "PC1"), ("OPERATIVO", "PC999")), session)


def test_repeated_queries_do_not_mutate(tmp_path):
    session = loaded_session(tmp_path)
    before = snapshot(session)
    query = ("COMPONENTES", "OPERATIVA")
    assert evaluate(query, session) == evaluate(query, session)
    assert snapshot(session) == before


def diagnostic_session(
    tmp_path: Path, events: dict[str, str], *, alternative: bool = False
) -> NetworkSession:
    devices = "Router1,10.0.0.1\nRouter2,10.0.0.2\nSwitch1,10.0.0.3\nSwitch2,10.0.0.4\nPC1,10.0.0.5\n"
    links = "Router1,Switch1\nSwitch1,Router2\n"
    if alternative:
        links += "Router1,Switch2\nSwitch2,Router2\n"
    event_text = "".join(f"{device}:{events.get(device, 'R')}\n" for device in ("Router1", "Router2", "Switch1", "Switch2", "PC1"))
    directory = write_data(tmp_path, devices, links, event_text, "diagnosis")
    session = NetworkSession()
    evaluate(("CARGAR",), session, data_dir=directory)
    return session


def test_diagnose_no_physical_path(tmp_path):
    result = evaluate(("DIAGNOSTICAR", "PC1", "Router1"), diagnostic_session(tmp_path, {}))
    assert isinstance(result, Diagnosis)
    assert result.no_physical_path and not result.communication_available
    assert not result.blocked_by_intermediaries


@pytest.mark.parametrize(
    ("events", "origin_failed", "destination_failed", "blocked"),
    [
        ({"Router1": "TT"}, True, False, False),
        ({"Router2": "TT"}, False, True, False),
        ({"Switch1": "TT"}, False, False, True),
        ({"Router1": "TT", "Router2": "TT", "Switch1": "TT"}, True, True, True),
    ],
)
def test_diagnose_independent_and_simultaneous_causes(
    tmp_path, events, origin_failed, destination_failed, blocked
):
    result = evaluate(
        ("DIAGNOSTICAR", "Router1", "Router2"), diagnostic_session(tmp_path, events)
    )
    assert result.origin_failed is origin_failed
    assert result.destination_failed is destination_failed
    assert result.blocked_by_intermediaries is blocked
    assert result.communication_available is False


def test_diagnose_checks_alternative_paths_and_same_origin(tmp_path):
    session = diagnostic_session(tmp_path, {"Switch1": "TT"}, alternative=True)
    alternative = evaluate(("DIAGNOSTICAR", "Router1", "Router2"), session)
    assert alternative.communication_available is True
    assert alternative.operational_route == Route(("Router1", "Switch2", "Router2"))
    assert alternative.blocked_by_intermediaries is False
    same = evaluate(("DIAGNOSTICAR", "Switch1", "Switch1"), session)
    assert same.physical_route == Route(("Switch1",))
    assert same.blocked_by_intermediaries is False


def test_diagnose_direct_link_has_no_failed_intermediaries(tmp_path):
    session = loaded_session(tmp_path)
    evaluate(("EVENTO", "PC1", "TT"), session)
    evaluate(("EVENTO", "Switch1", "TT"), session)
    result = evaluate(("DIAGNOSTICAR", "PC1", "Switch1"), session)
    assert result.origin_failed and result.destination_failed
    assert result.communication_available is False
    assert result.blocked_by_intermediaries is False


def test_direct_ast_semantic_errors_are_distinct(tmp_path):
    session = loaded_session(tmp_path)
    with pytest.raises(SemanticError):
        evaluate(("CAMINO", "PC1", "Server1", "MAGICA"), session)
    with pytest.raises(SemanticError):
        evaluate(("DESCONOCIDA",), session)
