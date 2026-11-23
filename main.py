"""Interactive console interface for the Network Graph Analyzer."""

from __future__ import annotations

from typing import Callable

from core.automata import HealthState
from core.domain import Connection, DomainError
from core.graph import Route
from core.loader import LoaderError
from core.session import NetworkSession, NoNetworkLoadedError
from language.evaluator import (
    DeviceView,
    Diagnosis,
    HealthView,
    LoadSummary,
    SemanticError,
    Visualization,
    execute,
)
from language.lexer import LexerError
from language.parser import ParserError
from visualization import (
    VisualizationDependencyError,
    build_figure,
    show_figure,
)


KNOWN_ERRORS = (
    LexerError,
    ParserError,
    SemanticError,
    DomainError,
    LoaderError,
    NoNetworkLoadedError,
    ValueError,
)


def _yes_no(value: bool) -> str:
    return "sí" if value else "no"


def _state_text(state: HealthState) -> str:
    return state.value


def _count_text(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _route_text(route: Route | None) -> str:
    if route is None:
        return "ninguna"
    suffix = "salto" if route.hops == 1 else "saltos"
    return f"{' -> '.join(route.path)} ({route.hops} {suffix})"


def _device_text(device: DeviceView) -> str:
    return (
        f"{device.device_id}: tipo={device.device_type}, IP={device.ip}, "
        f"diagnóstico={_state_text(device.health)}, "
        f"operativo={_yes_no(device.operational)}"
    )


def _health_text(health: HealthView) -> str:
    return (
        f"{health.device_id}: diagnóstico={_state_text(health.health)}, "
        f"operativo={_yes_no(health.operational)}"
    )


def _diagnosis_text(diagnosis: Diagnosis) -> str:
    causes: list[str] = []
    if diagnosis.no_physical_path:
        causes.append("no existe camino físico")
    if diagnosis.origin_failed:
        causes.append("origen en FAILURE")
    if diagnosis.destination_failed:
        causes.append("destino en FAILURE")
    if diagnosis.blocked_by_intermediaries:
        causes.append("intermediarios en FAILURE bloquean todos los caminos")
    cause_text = ", ".join(causes) if causes else "ninguna"
    return "\n".join(
        (
            f"Diagnóstico {diagnosis.origin} -> {diagnosis.destination}:",
            f"  Comunicación operativa: {_yes_no(diagnosis.communication_available)}",
            f"  Ruta física: {_route_text(diagnosis.physical_route)}",
            f"  Ruta operativa: {_route_text(diagnosis.operational_route)}",
            f"  Causas de interrupción: {cause_text}",
        )
    )


def _tuple_text(result: tuple, command: str) -> str:
    if result and all(isinstance(item, DeviceView) for item in result):
        return "Dispositivos:\n" + "\n".join(
            f"  {_device_text(item)}" for item in result
        )
    if result and all(isinstance(item, Connection) for item in result):
        return "Conexiones:\n" + "\n".join(
            f"  {item.first} -- {item.second}" for item in result
        )
    if command == "COMPONENTES":
        if not result:
            return "Componentes: ninguno"
        return "Componentes:\n" + "\n".join(
            f"  {index}: {', '.join(component)}"
            for index, component in enumerate(result, start=1)
        )

    labels = {
        "ESTADOS": "Dispositivos",
        "AISLADOS": "Aislados",
        "DISPOSITIVOS": "Dispositivos",
        "CONEXIONES": "Conexiones",
    }
    label = labels.get(command, "Resultados")
    return f"{label}: {', '.join(str(item) for item in result) if result else 'ninguno'}"


def format_result(result: object, instruction: str = "") -> str:
    """Format an evaluator result without applying domain decisions."""
    command = instruction.partition("(")[0].strip()
    if isinstance(result, LoadSummary):
        return (
            "Carga completada: "
            f"{_count_text(result.device_count, 'dispositivo', 'dispositivos')}, "
            f"{_count_text(result.connection_count, 'conexión', 'conexiones')}."
        )
    if isinstance(result, DeviceView):
        return _device_text(result)
    if isinstance(result, HealthView):
        return _health_text(result)
    if isinstance(result, Route):
        return f"Ruta: {_route_text(result)}"
    if isinstance(result, Diagnosis):
        return _diagnosis_text(result)
    if isinstance(result, Connection):
        return f"Conexión: {result.first} -- {result.second}"
    if isinstance(result, Visualization):
        return (
            "Visualización preparada: "
            f"{_count_text(len(result.devices), 'dispositivo', 'dispositivos')}, "
            f"{_count_text(len(result.connections), 'conexión', 'conexiones')}."
        )
    if isinstance(result, bool):
        return "Verdadero" if result else "Falso"
    if isinstance(result, int):
        return f"Grado: {result}" if command == "GRADO" else str(result)
    if result is None:
        if command == "CAMINO":
            return "No existe ruta."
        if command == "GRADO":
            return "Grado no aplicable."
        return "Sin resultado."
    if isinstance(result, tuple):
        return _tuple_text(result, command)
    return str(result)


def display_visualization(data: Visualization) -> None:
    """Build and show an evaluator visualization without blocking the CLI."""
    show_figure(build_figure(data))


def run_cli(
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
    visualization_func: Callable[[Visualization], None] = display_visualization,
) -> None:
    """Run a stateful read-evaluate-print loop until the user enters SALIR."""
    session = NetworkSession()
    output_func("Network Graph Analyzer. Escribe SALIR para terminar.")

    while True:
        try:
            source = input_func("nga> ")
        except (EOFError, KeyboardInterrupt):
            output_func("Hasta luego.")
            return

        instruction = source.strip()
        if not instruction:
            continue
        if instruction == "SALIR":
            output_func("Hasta luego.")
            return

        try:
            result = execute(instruction, session)
        except KNOWN_ERRORS as exc:
            output_func(f"Error: {exc}")
            continue

        if isinstance(result, Visualization):
            try:
                visualization_func(result)
            except VisualizationDependencyError as exc:
                output_func(f"Error de visualización: {exc}")
                continue

        output_func(format_result(result, instruction))


if __name__ == "__main__":
    run_cli()
