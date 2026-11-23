"""Table-driven LL(1) parser and tuple AST builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import MutableSequence

from lexer import LexerError, Token, TokenType, tokenize


NonTerminal = str
GrammarSymbol = NonTerminal | TokenType
NON_TERMINALS = frozenset({"S", "ADMIN", "INFO", "BOOL", "ESTADO", "MODO"})
VALUE_TERMINALS = frozenset(
    {
        TokenType.ID,
        TokenType.IP,
        TokenType.SEQ,
        TokenType.NORMAL,
        TokenType.WARNING,
        TokenType.FAILURE,
        TokenType.FISICA,
        TokenType.OPERATIVA,
    }
)


@dataclass(frozen=True, slots=True)
class _BuildAction:
    name: str
    arity: int


@dataclass(frozen=True, slots=True)
class Production:
    left: NonTerminal
    right: tuple[GrammarSymbol, ...]
    build: _BuildAction | None = None


@dataclass(frozen=True, slots=True)
class TraceStep:
    position: int
    lookahead: str
    stack: tuple[str, ...]
    action: str


@dataclass(frozen=True, slots=True)
class ParseTrace:
    accepted: bool
    ast: tuple | None
    steps: tuple[TraceStep, ...]
    error: str | None


class ParserError(Exception):
    """Raised when the token stream does not match the LL(1) grammar."""

    def __init__(
        self, position: int, found: Token, expected: tuple[str, ...], message: str = ""
    ) -> None:
        self.position = position
        self.found = found
        self.expected = expected
        found_text = found.lexeme or "fin de entrada"
        expected_text = ", ".join(expected)
        detail = message or f"se esperaba {expected_text}; se encontró {found_text!r}"
        super().__init__(f"posición {position}: {detail}")


def _p(
    left: NonTerminal,
    right: tuple[GrammarSymbol, ...],
    name: str | None = None,
    arity: int = 0,
) -> Production:
    return Production(left, right, None if name is None else _BuildAction(name, arity))


PRODUCTIONS: dict[str, Production] = {
    "S_ADMIN": _p("S", ("ADMIN",)),
    "S_INFO": _p("S", ("INFO",)),
    "S_BOOL": _p("S", ("BOOL",)),
    "ADMIN_CARGAR": _p(
        "ADMIN", (TokenType.CARGAR, TokenType.LPAREN, TokenType.RPAREN), "CARGAR"
    ),
    "ADMIN_REGISTRAR": _p(
        "ADMIN",
        (
            TokenType.REGISTRAR,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.IP,
            TokenType.COMMA,
            TokenType.SEQ,
            TokenType.RPAREN,
        ),
        "REGISTRAR",
        3,
    ),
    "ADMIN_CAMBIAR_IP": _p(
        "ADMIN",
        (
            TokenType.CAMBIAR_IP,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.IP,
            TokenType.RPAREN,
        ),
        "CAMBIAR_IP",
        2,
    ),
    "ADMIN_CONECTAR": _p(
        "ADMIN",
        (
            TokenType.CONECTAR,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.ID,
            TokenType.RPAREN,
        ),
        "CONECTAR",
        2,
    ),
    "ADMIN_DESCONECTAR": _p(
        "ADMIN",
        (
            TokenType.DESCONECTAR,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.ID,
            TokenType.RPAREN,
        ),
        "DESCONECTAR",
        2,
    ),
    "ADMIN_EVENTO": _p(
        "ADMIN",
        (
            TokenType.EVENTO,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.SEQ,
            TokenType.RPAREN,
        ),
        "EVENTO",
        2,
    ),
    "INFO_SALUD": _p(
        "INFO", (TokenType.SALUD, TokenType.LPAREN, TokenType.ID, TokenType.RPAREN), "SALUD", 1
    ),
    "INFO_ESTADOS": _p(
        "INFO", (TokenType.ESTADOS, TokenType.LPAREN, "ESTADO", TokenType.RPAREN), "ESTADOS", 1
    ),
    "INFO_CAMINO": _p(
        "INFO",
        (
            TokenType.CAMINO,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.ID,
            TokenType.COMMA,
            "MODO",
            TokenType.RPAREN,
        ),
        "CAMINO",
        3,
    ),
    "INFO_DIAGNOSTICAR": _p(
        "INFO",
        (
            TokenType.DIAGNOSTICAR,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.ID,
            TokenType.RPAREN,
        ),
        "DIAGNOSTICAR",
        2,
    ),
    "INFO_GRADO": _p(
        "INFO",
        (
            TokenType.GRADO,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            "MODO",
            TokenType.RPAREN,
        ),
        "GRADO",
        2,
    ),
    "INFO_AISLADOS": _p(
        "INFO", (TokenType.AISLADOS, TokenType.LPAREN, "MODO", TokenType.RPAREN), "AISLADOS", 1
    ),
    "INFO_COMPONENTES": _p(
        "INFO",
        (TokenType.COMPONENTES, TokenType.LPAREN, "MODO", TokenType.RPAREN),
        "COMPONENTES",
        1,
    ),
    "INFO_DISPOSITIVOS": _p(
        "INFO", (TokenType.DISPOSITIVOS, TokenType.LPAREN, TokenType.RPAREN), "DISPOSITIVOS"
    ),
    "INFO_CONEXIONES": _p(
        "INFO", (TokenType.CONEXIONES, TokenType.LPAREN, TokenType.RPAREN), "CONEXIONES"
    ),
    "INFO_VISUALIZAR": _p(
        "INFO", (TokenType.VISUALIZAR, TokenType.LPAREN, TokenType.RPAREN), "VISUALIZAR"
    ),
    "BOOL_OPERATIVO": _p(
        "BOOL", (TokenType.OPERATIVO, TokenType.LPAREN, TokenType.ID, TokenType.RPAREN), "OPERATIVO", 1
    ),
    "BOOL_ES_ESTADO": _p(
        "BOOL",
        (
            TokenType.ES_ESTADO,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            "ESTADO",
            TokenType.RPAREN,
        ),
        "ES_ESTADO",
        2,
    ),
    "BOOL_RUTA": _p(
        "BOOL",
        (
            TokenType.RUTA,
            TokenType.LPAREN,
            TokenType.ID,
            TokenType.COMMA,
            TokenType.ID,
            TokenType.COMMA,
            "MODO",
            TokenType.RPAREN,
        ),
        "RUTA",
        3,
    ),
    "BOOL_Y": _p(
        "BOOL",
        (TokenType.Y, TokenType.LPAREN, "BOOL", TokenType.COMMA, "BOOL", TokenType.RPAREN),
        "Y",
        2,
    ),
    "BOOL_O": _p(
        "BOOL",
        (TokenType.O, TokenType.LPAREN, "BOOL", TokenType.COMMA, "BOOL", TokenType.RPAREN),
        "O",
        2,
    ),
    "ESTADO_NORMAL": _p("ESTADO", (TokenType.NORMAL,)),
    "ESTADO_WARNING": _p("ESTADO", (TokenType.WARNING,)),
    "ESTADO_FAILURE": _p("ESTADO", (TokenType.FAILURE,)),
    "MODO_FISICA": _p("MODO", (TokenType.FISICA,)),
    "MODO_OPERATIVA": _p("MODO", (TokenType.OPERATIVA,)),
}


ADMIN_FIRST = (
    TokenType.CARGAR,
    TokenType.REGISTRAR,
    TokenType.CAMBIAR_IP,
    TokenType.CONECTAR,
    TokenType.DESCONECTAR,
    TokenType.EVENTO,
)
INFO_FIRST = (
    TokenType.SALUD,
    TokenType.ESTADOS,
    TokenType.CAMINO,
    TokenType.DIAGNOSTICAR,
    TokenType.GRADO,
    TokenType.AISLADOS,
    TokenType.COMPONENTES,
    TokenType.DISPOSITIVOS,
    TokenType.CONEXIONES,
    TokenType.VISUALIZAR,
)
BOOL_FIRST = (
    TokenType.OPERATIVO,
    TokenType.ES_ESTADO,
    TokenType.RUTA,
    TokenType.Y,
    TokenType.O,
)


PARSE_TABLE: dict[tuple[NonTerminal, TokenType], str] = {}
for token_type in ADMIN_FIRST:
    PARSE_TABLE[("S", token_type)] = "S_ADMIN"
for token_type in INFO_FIRST:
    PARSE_TABLE[("S", token_type)] = "S_INFO"
for token_type in BOOL_FIRST:
    PARSE_TABLE[("S", token_type)] = "S_BOOL"
for token_type, production in zip(
    ADMIN_FIRST,
    (
        "ADMIN_CARGAR",
        "ADMIN_REGISTRAR",
        "ADMIN_CAMBIAR_IP",
        "ADMIN_CONECTAR",
        "ADMIN_DESCONECTAR",
        "ADMIN_EVENTO",
    ),
    strict=True,
):
    PARSE_TABLE[("ADMIN", token_type)] = production
for token_type, production in zip(
    INFO_FIRST,
    (
        "INFO_SALUD",
        "INFO_ESTADOS",
        "INFO_CAMINO",
        "INFO_DIAGNOSTICAR",
        "INFO_GRADO",
        "INFO_AISLADOS",
        "INFO_COMPONENTES",
        "INFO_DISPOSITIVOS",
        "INFO_CONEXIONES",
        "INFO_VISUALIZAR",
    ),
    strict=True,
):
    PARSE_TABLE[("INFO", token_type)] = production
for token_type, production in zip(
    BOOL_FIRST,
    ("BOOL_OPERATIVO", "BOOL_ES_ESTADO", "BOOL_RUTA", "BOOL_Y", "BOOL_O"),
    strict=True,
):
    PARSE_TABLE[("BOOL", token_type)] = production
for token_type, production in (
    (TokenType.NORMAL, "ESTADO_NORMAL"),
    (TokenType.WARNING, "ESTADO_WARNING"),
    (TokenType.FAILURE, "ESTADO_FAILURE"),
):
    PARSE_TABLE[("ESTADO", token_type)] = production
for token_type, production in (
    (TokenType.FISICA, "MODO_FISICA"),
    (TokenType.OPERATIVA, "MODO_OPERATIVA"),
):
    PARSE_TABLE[("MODO", token_type)] = production


def _symbol_text(symbol: GrammarSymbol | _BuildAction) -> str:
    if isinstance(symbol, TokenType):
        return symbol.value
    if isinstance(symbol, _BuildAction):
        return f"@{symbol.name}/{symbol.arity}"
    return symbol


def _record(
    trace: MutableSequence[TraceStep] | None,
    token: Token,
    stack: list[GrammarSymbol | _BuildAction],
    action: str,
) -> None:
    if trace is not None:
        trace.append(
            TraceStep(
                token.position,
                token.lexeme or "<EOF>",
                tuple(_symbol_text(symbol) for symbol in reversed(stack)),
                action,
            )
        )


def parse(source: str, trace: MutableSequence[TraceStep] | None = None) -> tuple:
    """Parse source with an explicit LL(1) stack and build its tuple AST."""
    tokens = tokenize(source)
    stack: list[GrammarSymbol | _BuildAction] = [TokenType.EOF, "S"]
    semantic: list[str | tuple] = []
    index = 0

    while stack:
        lookahead = tokens[index]
        symbol = stack.pop()

        if isinstance(symbol, _BuildAction):
            if symbol.arity:
                arguments = semantic[-symbol.arity :]
                del semantic[-symbol.arity :]
            else:
                arguments = []
            semantic.append((symbol.name, *arguments))
            _record(trace, lookahead, stack, f"construir AST {symbol.name}/{symbol.arity}")
            continue

        if isinstance(symbol, TokenType):
            if lookahead.type is not symbol:
                error = ParserError(lookahead.position, lookahead, (symbol.value,))
                _record(trace, lookahead, stack, f"rechazar: {error}")
                raise error
            if symbol in VALUE_TERMINALS:
                semantic.append(lookahead.lexeme)
            _record(trace, lookahead, stack, f"consumir {symbol.value}")
            index += 1
            continue

        production_name = PARSE_TABLE.get((symbol, lookahead.type))
        if production_name is None:
            expected = tuple(
                token_type.value
                for non_terminal, token_type in PARSE_TABLE
                if non_terminal == symbol
            )
            error = ParserError(lookahead.position, lookahead, expected)
            _record(trace, lookahead, stack, f"rechazar: {error}")
            raise error

        production = PRODUCTIONS[production_name]
        if production.build is not None:
            stack.append(production.build)
        stack.extend(reversed(production.right))
        right_text = " ".join(_symbol_text(item) for item in production.right)
        _record(trace, lookahead, stack, f"aplicar {production.left} → {right_text}")

    if index != len(tokens):
        lookahead = tokens[index]
        error = ParserError(
            lookahead.position, lookahead, ("fin de entrada",), "entrada sobrante"
        )
        _record(trace, lookahead, stack, f"rechazar: {error}")
        raise error
    if len(semantic) != 1 or not isinstance(semantic[0], tuple):
        raise RuntimeError("Parser finished without exactly one AST.")
    _record(trace, tokens[-1], stack, "aceptar")
    return semantic[0]


def trace_parse(source: str) -> ParseTrace:
    """Return the exact trace produced by the parser for acceptance or rejection."""
    steps: list[TraceStep] = []
    try:
        ast = parse(source, steps)
        return ParseTrace(True, ast, tuple(steps), None)
    except (LexerError, ParserError) as exc:
        if not steps:
            position = getattr(exc, "position", 0)
            steps.append(TraceStep(position, "<LEXICAL_ERROR>", (), f"rechazar: {exc}"))
        return ParseTrace(False, None, tuple(steps), str(exc))
