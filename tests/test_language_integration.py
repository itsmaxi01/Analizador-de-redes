from pathlib import Path

import pytest

from automata import HealthState
from domain import DeviceNotFoundError
from evaluator import Diagnosis, DeviceView, HealthView, LoadSummary, execute
from graph import Route
from lexer import LexerError
from parser import ParserError
from session import NetworkSession


def language_data(tmp_path: Path) -> Path:
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "devices.txt").write_text(
        "Router1,10.0.0.1\nSwitch1,10.0.0.2\nPC1,10.0.0.3\nServer1,10.0.0.4\n",
        encoding="utf-8",
    )
    (directory / "connections.txt").write_text(
        "Router1,Switch1\nSwitch1,PC1\nSwitch1,Server1\n", encoding="utf-8"
    )
    (directory / "events.txt").write_text(
        "Router1:R\nSwitch1:R\nPC1:R\nServer1:R\n", encoding="utf-8"
    )
    return directory


def test_end_to_end_all_instruction_families(tmp_path):
    session = NetworkSession()
    data = language_data(tmp_path)
    assert execute("CARGAR()", session, data_dir=data) == LoadSummary(4, 3)
    assert execute("REGISTRAR(PC2,10.0.0.5,T)", session) == DeviceView(
        "PC2", "PC", "10.0.0.5", HealthState.WARNING, True
    )
    assert execute("CAMBIAR_IP(PC2,172.16.0.5)", session).ip == "172.16.0.5"
    assert execute("CONECTAR(Switch1,PC2)", session).endpoints == frozenset({"Switch1", "PC2"})
    assert execute("DESCONECTAR(PC2,Switch1)", session).endpoints == frozenset({"Switch1", "PC2"})
    assert execute("EVENTO(PC2,T)", session) == HealthView(
        "PC2", HealthState.FAILURE, False
    )
    assert execute("SALUD(PC2)", session).health is HealthState.FAILURE
    assert execute("ESTADOS(FAILURE)", session) == ("PC2",)
    assert execute("CAMINO(PC1,Router1,FISICA)", session) == Route(("PC1", "Switch1", "Router1"))
    assert isinstance(execute("DIAGNOSTICAR(PC1,Server1)", session), Diagnosis)
    assert execute("GRADO(PC1,FISICA)", session) == 1
    assert execute("AISLADOS(FISICA)", session) == ("PC2",)
    assert execute("COMPONENTES(FISICA)", session)[1] == ("PC2",)
    assert len(execute("DISPOSITIVOS()", session)) == 5
    assert len(execute("CONEXIONES()", session)) == 3
    assert len(execute("VISUALIZAR()", session).devices) == 5
    assert execute("OPERATIVO(PC1)", session) is True
    assert execute("ES_ESTADO(PC2,FAILURE)", session) is True
    assert execute("RUTA(PC1,Server1,OPERATIVA)", session) is True
    assert execute("Y(OPERATIVO(PC1),ES_ESTADO(PC2,FAILURE))", session) is True
    assert execute("O(OPERATIVO(PC2),RUTA(PC1,Server1,FISICA))", session) is True


def test_execute_preserves_lexical_syntactic_and_domain_error_types(tmp_path):
    session = NetworkSession()
    execute("CARGAR()", session, data_dir=language_data(tmp_path))
    with pytest.raises(LexerError):
        execute("OPERATIVO(@)", session)
    with pytest.raises(ParserError):
        execute("OPERATIVO(PC1,PC2)", session)
    with pytest.raises(DeviceNotFoundError):
        execute("OPERATIVO(PC999)", session)


def test_end_to_end_short_circuit_still_validates_every_identifier(tmp_path):
    session = NetworkSession()
    execute("CARGAR()", session, data_dir=language_data(tmp_path))
    with pytest.raises(DeviceNotFoundError):
        execute("O(OPERATIVO(PC1),OPERATIVO(PC999))", session)
