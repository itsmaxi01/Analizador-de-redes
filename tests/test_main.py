import pytest

from core.automata import HealthState
from core.domain import Connection
from core.graph import Route
from language.evaluator import DeviceView, Diagnosis, HealthView, LoadSummary
from main import format_result, run_cli


def run_commands(*instructions: str) -> list[str]:
    pending = iter((*instructions, "SALIR"))
    output: list[str] = []
    run_cli(lambda _: next(pending), output.append)
    return output


def test_cli_starts_and_salir_ends_without_loading():
    output = run_commands()
    assert output == [
        "Network Graph Analyzer. Escribe SALIR para terminar.",
        "Hasta luego.",
    ]


def test_cli_keeps_session_across_multiple_instructions():
    output = run_commands("CARGAR()", "EVENTO(PC1,T)", "SALUD(PC1)")
    assert output[1] == "Carga completada: 7 dispositivos, 6 conexiones."
    assert output[2] == "PC1: diagnóstico=WARNING, operativo=sí"
    assert output[3] == "PC1: diagnóstico=WARNING, operativo=sí"


def test_expected_error_does_not_close_cli():
    output = run_commands("CARGAR()", "OPERATIVO(PC999)", "OPERATIVO(PC1)")
    assert output[2].startswith("Error: Device 'PC999'")
    assert output[3] == "Verdadero"
    assert output[-1] == "Hasta luego."


@pytest.mark.parametrize("exception", [EOFError(), KeyboardInterrupt()])
def test_eof_and_keyboard_interrupt_exit_cleanly(exception):
    output: list[str] = []

    def stop(_):
        raise exception

    run_cli(stop, output.append)
    assert output[-1] == "Hasta luego."


def test_cli_formats_boolean_and_missing_route():
    output = run_commands(
        "CARGAR()",
        "OPERATIVO(PC1)",
        "RUTA(PC1,PC3,FISICA)",
        "CAMINO(PC1,PC3,FISICA)",
    )
    assert output[2] == "Verdadero"
    assert output[3] == "Falso"
    assert output[4] == "No existe ruta."


def test_format_result_covers_typed_results_and_none_context():
    device = DeviceView("PC1", "PC", "10.0.0.1", HealthState.NORMAL, True)
    assert format_result(LoadSummary(2, 1), "CARGAR()") == (
        "Carga completada: 2 dispositivos, 1 conexión."
    )
    assert "tipo=PC" in format_result(device, "REGISTRAR(PC1,10.0.0.1,R)")
    assert format_result(
        HealthView("PC1", HealthState.FAILURE, False), "SALUD(PC1)"
    ) == "PC1: diagnóstico=FAILURE, operativo=no"
    assert format_result(
        Route(("PC1", "Switch1")), "CAMINO(PC1,Switch1,FISICA)"
    ) == "Ruta: PC1 -> Switch1 (1 salto)"
    assert format_result(Connection("PC1", "Switch1"), "CONECTAR(PC1,Switch1)") == (
        "Conexión: PC1 -- Switch1"
    )
    assert format_result(3, "GRADO(Switch1,FISICA)") == "Grado: 3"
    assert format_result(None, "GRADO(PC1,OPERATIVA)") == "Grado no aplicable."


def test_format_result_describes_diagnosis_causes():
    diagnosis = Diagnosis(
        origin="PC1",
        destination="Server1",
        physical_route=Route(("PC1", "Switch1", "Server1")),
        operational_route=None,
        communication_available=False,
        no_physical_path=False,
        origin_failed=True,
        destination_failed=False,
        blocked_by_intermediaries=True,
    )
    text = format_result(diagnosis, "DIAGNOSTICAR(PC1,Server1)")
    assert "Comunicación operativa: no" in text
    assert "origen en FAILURE" in text
    assert "intermediarios en FAILURE" in text


def test_format_result_handles_collections():
    assert format_result(("PC1", "PC2"), "AISLADOS(FISICA)") == (
        "Aislados: PC1, PC2"
    )
    assert format_result(
        (("PC1",), ("PC2", "Switch1")), "COMPONENTES(FISICA)"
    ) == "Componentes:\n  1: PC1\n  2: PC2, Switch1"
    devices = (
        DeviceView("PC1", "PC", "10.0.0.1", HealthState.NORMAL, True),
    )
    assert "PC1: tipo=PC" in format_result(devices, "DISPOSITIVOS()")
    connections = (Connection("PC1", "Switch1"),)
    assert format_result(connections, "CONEXIONES()") == (
        "Conexiones:\n  PC1 -- Switch1"
    )
