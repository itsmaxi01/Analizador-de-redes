"""Semantic evaluator and interpreter for the Network Graph Analyzer language."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from language import parser
from core.automata import HealthState
from core.domain import Connection, Device, Network
from core.graph import (
    GraphMode,
    Route,
    connected_components,
    degree,
    is_connected,
    isolated_nodes,
    shortest_path,
    shortest_path_with_operational_intermediates,
)
from core.session import NetworkSession


DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_BOOLEAN_OPERATIONS = frozenset({"OPERATIVO", "ES_ESTADO", "RUTA", "Y", "O"})


class SemanticError(Exception):
    """Raised when a tuple is not a valid evaluable language AST."""


@dataclass(frozen=True, slots=True)
class LoadSummary:
    device_count: int
    connection_count: int


@dataclass(frozen=True, slots=True)
class DeviceView:
    device_id: str
    device_type: str
    ip: str
    health: HealthState
    operational: bool


@dataclass(frozen=True, slots=True)
class HealthView:
    device_id: str
    health: HealthState
    operational: bool


@dataclass(frozen=True, slots=True)
class Diagnosis:
    origin: str
    destination: str
    physical_route: Route | None
    operational_route: Route | None
    communication_available: bool
    no_physical_path: bool
    origin_failed: bool
    destination_failed: bool
    blocked_by_intermediaries: bool


@dataclass(frozen=True, slots=True)
class Visualization:
    devices: tuple[DeviceView, ...]
    connections: tuple[Connection, ...]


def _device_view(device: Device) -> DeviceView:
    return DeviceView(
        device.id, device.type, device.ip, device.health, device.operational
    )


def _health_view(device: Device) -> HealthView:
    return HealthView(device.id, device.health, device.operational)


def _devices(network: Network) -> tuple[DeviceView, ...]:
    return tuple(_device_view(network.devices[device_id]) for device_id in sorted(network.devices))


def _connections(network: Network) -> tuple[Connection, ...]:
    return tuple(sorted(network.connections, key=lambda link: (link.first, link.second)))


def _operation(ast: tuple) -> str:
    if not isinstance(ast, tuple) or not ast or not isinstance(ast[0], str):
        raise SemanticError("The evaluator requires a non-empty tuple AST.")
    return ast[0]


def _require_arity(ast: tuple, arity: int) -> None:
    if len(ast) != arity + 1:
        raise SemanticError(
            f"Operation {_operation(ast)!r} expects {arity} arguments, got {len(ast) - 1}."
        )


def _mode(value: object) -> GraphMode:
    try:
        return GraphMode(value)
    except (TypeError, ValueError) as exc:
        raise SemanticError(f"Unknown graph mode {value!r}.") from exc


def _state(value: object) -> HealthState:
    try:
        return HealthState(value)
    except (TypeError, ValueError) as exc:
        raise SemanticError(f"Unknown health state {value!r}.") from exc


def _boolean_device_ids(ast: tuple) -> tuple[str, ...]:
    operation = _operation(ast)
    if operation == "OPERATIVO":
        _require_arity(ast, 1)
        return (ast[1],)
    if operation == "ES_ESTADO":
        _require_arity(ast, 2)
        _state(ast[2])
        return (ast[1],)
    if operation == "RUTA":
        _require_arity(ast, 3)
        _mode(ast[3])
        return (ast[1], ast[2])
    if operation in {"Y", "O"}:
        _require_arity(ast, 2)
        if not isinstance(ast[1], tuple) or not isinstance(ast[2], tuple):
            raise SemanticError(f"Operation {operation!r} requires two boolean AST operands.")
        return _boolean_device_ids(ast[1]) + _boolean_device_ids(ast[2])
    raise SemanticError(f"Operation {operation!r} is not a boolean expression.")


def _eval_boolean(ast: tuple, network: Network) -> bool:
    operation = _operation(ast)
    if operation == "OPERATIVO":
        return network.get_device(ast[1]).operational
    if operation == "ES_ESTADO":
        return network.get_device(ast[1]).health is _state(ast[2])
    if operation == "RUTA":
        return is_connected(network, ast[1], ast[2], _mode(ast[3]))
    if operation == "Y":
        return _eval_boolean(ast[1], network) and _eval_boolean(ast[2], network)
    if operation == "O":
        return _eval_boolean(ast[1], network) or _eval_boolean(ast[2], network)
    raise SemanticError(f"Operation {operation!r} is not a boolean expression.")


def _evaluate_boolean(ast: tuple, network: Network) -> bool:
    referenced_ids = _boolean_device_ids(ast)
    for device_id in referenced_ids:
        network.get_device(device_id)
    return _eval_boolean(ast, network)


def _diagnose(network: Network, origin: str, destination: str) -> Diagnosis:
    origin_device = network.get_device(origin)
    destination_device = network.get_device(destination)
    physical_route = shortest_path(network, origin, destination, GraphMode.FISICA)
    operational_route = shortest_path(network, origin, destination, GraphMode.OPERATIVA)
    intermediates_route = (
        shortest_path_with_operational_intermediates(network, origin, destination)
        if physical_route is not None
        else None
    )
    return Diagnosis(
        origin=origin,
        destination=destination,
        physical_route=physical_route,
        operational_route=operational_route,
        communication_available=operational_route is not None,
        no_physical_path=physical_route is None,
        origin_failed=not origin_device.operational,
        destination_failed=not destination_device.operational,
        blocked_by_intermediaries=(
            physical_route is not None and intermediates_route is None
        ),
    )


def evaluate(
    ast: tuple,
    session: NetworkSession,
    *,
    data_dir: Path | None = None,
) -> object:
    """Evaluate one syntactically valid tuple AST against a session."""
    operation = _operation(ast)

    if operation == "CARGAR":
        _require_arity(ast, 0)
        directory = DEFAULT_DATA_DIR if data_dir is None else Path(data_dir)
        network = session.load(
            directory / "devices.txt",
            directory / "connections.txt",
            directory / "events.txt",
        )
        return LoadSummary(len(network.devices), len(network.connections))

    network = session.require_network()
    if operation in _BOOLEAN_OPERATIONS:
        return _evaluate_boolean(ast, network)

    if operation == "REGISTRAR":
        _require_arity(ast, 3)
        return _device_view(network.register_device(ast[1], ast[2], ast[3]))
    if operation == "CAMBIAR_IP":
        _require_arity(ast, 2)
        network.change_ip(ast[1], ast[2])
        return _device_view(network.get_device(ast[1]))
    if operation == "CONECTAR":
        _require_arity(ast, 2)
        return network.connect(ast[1], ast[2])
    if operation == "DESCONECTAR":
        _require_arity(ast, 2)
        return network.disconnect(ast[1], ast[2])
    if operation == "EVENTO":
        _require_arity(ast, 2)
        network.register_health(ast[1], ast[2])
        return _health_view(network.get_device(ast[1]))
    if operation == "SALUD":
        _require_arity(ast, 1)
        return _health_view(network.get_device(ast[1]))
    if operation == "ESTADOS":
        _require_arity(ast, 1)
        state = _state(ast[1])
        return tuple(
            device_id
            for device_id in sorted(network.devices)
            if network.devices[device_id].health is state
        )
    if operation == "CAMINO":
        _require_arity(ast, 3)
        return shortest_path(network, ast[1], ast[2], _mode(ast[3]))
    if operation == "DIAGNOSTICAR":
        _require_arity(ast, 2)
        return _diagnose(network, ast[1], ast[2])
    if operation == "GRADO":
        _require_arity(ast, 2)
        return degree(network, ast[1], _mode(ast[2]))
    if operation == "AISLADOS":
        _require_arity(ast, 1)
        return isolated_nodes(network, _mode(ast[1]))
    if operation == "COMPONENTES":
        _require_arity(ast, 1)
        return connected_components(network, _mode(ast[1]))
    if operation == "DISPOSITIVOS":
        _require_arity(ast, 0)
        return _devices(network)
    if operation == "CONEXIONES":
        _require_arity(ast, 0)
        return _connections(network)
    if operation == "VISUALIZAR":
        _require_arity(ast, 0)
        return Visualization(_devices(network), _connections(network))

    raise SemanticError(f"Unknown AST operation {operation!r}.")


def execute(
    source: str,
    session: NetworkSession,
    *,
    data_dir: Path | None = None,
) -> object:
    """Parse and execute one complete language instruction."""
    return evaluate(parser.parse(source), session, data_dir=data_dir)
