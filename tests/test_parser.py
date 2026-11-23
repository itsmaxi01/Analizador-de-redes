import pytest

from lexer import LexerError
from parser import ParserError, parse, trace_parse


VALID_CONSTRUCTIONS = [
    ("CARGAR()", ("CARGAR",)),
    ("REGISTRAR(PC1,192.168.1.10,RRT)", ("REGISTRAR", "PC1", "192.168.1.10", "RRT")),
    ("CAMBIAR_IP(PC1,8.8.8.8)", ("CAMBIAR_IP", "PC1", "8.8.8.8")),
    ("CONECTAR(Switch1,PC1)", ("CONECTAR", "Switch1", "PC1")),
    ("DESCONECTAR(Switch1,PC1)", ("DESCONECTAR", "Switch1", "PC1")),
    ("EVENTO(Switch1,RRT)", ("EVENTO", "Switch1", "RRT")),
    ("SALUD(PC1)", ("SALUD", "PC1")),
    ("ESTADOS(WARNING)", ("ESTADOS", "WARNING")),
    ("CAMINO(PC1,Server1,FISICA)", ("CAMINO", "PC1", "Server1", "FISICA")),
    ("DIAGNOSTICAR(PC1,Server1)", ("DIAGNOSTICAR", "PC1", "Server1")),
    ("GRADO(Switch1,OPERATIVA)", ("GRADO", "Switch1", "OPERATIVA")),
    ("AISLADOS(FISICA)", ("AISLADOS", "FISICA")),
    ("COMPONENTES(OPERATIVA)", ("COMPONENTES", "OPERATIVA")),
    ("DISPOSITIVOS()", ("DISPOSITIVOS",)),
    ("CONEXIONES()", ("CONEXIONES",)),
    ("VISUALIZAR()", ("VISUALIZAR",)),
    ("OPERATIVO(PC1)", ("OPERATIVO", "PC1")),
    ("ES_ESTADO(Switch1,FAILURE)", ("ES_ESTADO", "Switch1", "FAILURE")),
    ("RUTA(PC1,Server1,OPERATIVA)", ("RUTA", "PC1", "Server1", "OPERATIVA")),
    ("Y(OPERATIVO(PC1),RUTA(PC1,Server1,OPERATIVA))", ("Y", ("OPERATIVO", "PC1"), ("RUTA", "PC1", "Server1", "OPERATIVA"))),
    ("O(OPERATIVO(PC1),ES_ESTADO(Switch1,NORMAL))", ("O", ("OPERATIVO", "PC1"), ("ES_ESTADO", "Switch1", "NORMAL"))),
]


@pytest.mark.parametrize("source, expected", VALID_CONSTRUCTIONS)
def test_all_21_constructions(source, expected):
    assert parse(source) == expected


def test_multiple_boolean_nesting_levels_and_spaces():
    source = " Y ( OPERATIVO ( PC1 ) , O ( ES_ESTADO ( Switch1 , WARNING ) , RUTA ( PC1 , Server1 , FISICA ) ) ) "
    assert parse(source) == (
        "Y",
        ("OPERATIVO", "PC1"),
        (
            "O",
            ("ES_ESTADO", "Switch1", "WARNING"),
            ("RUTA", "PC1", "Server1", "FISICA"),
        ),
    )


INVALID_SYNTAX = [
    ("", "entrada vacía"),
    ("OPERATIVO(PC1", "falta paréntesis de cierre"),
    ("Y(OPERATIVO(PC1))", "falta coma y segunda expresión"),
    ("RUTA(PC1,Server1)", "falta argumento MODO"),
    ("CARGAR())", "paréntesis adicional"),
    ("CONECTAR(PC1,,Switch1)", "coma duplicada"),
    ("SALUD(PC1,PC2)", "argumento adicional"),
    ("GRADO(PC1,NORMAL)", "categoría ESTADO donde se esperaba MODO"),
    ("ESTADOS(OPERATIVA)", "categoría MODO donde se esperaba ESTADO"),
    ("OPERATIVO(PC1) OPERATIVO(PC2)", "entrada sobrante"),
]


@pytest.mark.parametrize("source, justification", INVALID_SYNTAX, ids=[item[1] for item in INVALID_SYNTAX])
def test_invalid_syntax_cases(source, justification):
    with pytest.raises(ParserError):
        parse(source)


@pytest.mark.parametrize(
    "source, justification",
    [
        ("operativo(PC1)", "mayúsculas incorrectas"),
        ("OPERATIVO(PC0)", "ID inválido"),
        ("EVENTO(PC1,RX)", "secuencia inválida"),
        ("CAMBIAR_IP(PC1,256.1.1.1)", "IPv4 inválida"),
        ("OPERATIVO(PC1)@", "carácter desconocido"),
        ("NUEVO(PC1)", "palabra reservada desconocida"),
    ],
)
def test_invalid_lexical_cases(source, justification):
    with pytest.raises(LexerError):
        parse(source)


def test_syntactically_valid_values_are_not_semantically_checked():
    assert parse("CAMBIAR_IP(PC999,8.8.8.8)") == (
        "CAMBIAR_IP",
        "PC999",
        "8.8.8.8",
    )


@pytest.mark.parametrize(
    "source",
    [
        "CARGAR()",
        "EVENTO(Switch1,RRT)",
        "Y(OPERATIVO(PC1),O(ES_ESTADO(Switch1,FAILURE),RUTA(PC1,Server1,OPERATIVA)))",
    ],
)
def test_three_acceptance_traces(source):
    result = trace_parse(source)
    assert result.accepted
    assert result.ast == parse(source)
    assert result.steps[-1].action == "aceptar"
    assert any(step.action.startswith("aplicar") for step in result.steps)
    assert any(step.action.startswith("consumir") for step in result.steps)


@pytest.mark.parametrize(
    "source",
    [
        "OPERATIVO(PC1",
        "Y(OPERATIVO(PC1))",
        "RUTA(PC1,Server1)",
    ],
)
def test_three_rejection_traces(source):
    result = trace_parse(source)
    assert not result.accepted
    assert result.ast is None
    assert result.error is not None
    assert result.steps[-1].action.startswith("rechazar")
