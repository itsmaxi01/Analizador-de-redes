"""Strict lexer for the Network Graph Analyzer command language."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.validators import DEVICE_ID_PATTERN, HEALTH_EVENTS_PATTERN, IPV4_PATTERN


class TokenType(str, Enum):
    CARGAR = "CARGAR"
    REGISTRAR = "REGISTRAR"
    CAMBIAR_IP = "CAMBIAR_IP"
    CONECTAR = "CONECTAR"
    DESCONECTAR = "DESCONECTAR"
    EVENTO = "EVENTO"
    SALUD = "SALUD"
    ESTADOS = "ESTADOS"
    CAMINO = "CAMINO"
    DIAGNOSTICAR = "DIAGNOSTICAR"
    GRADO = "GRADO"
    AISLADOS = "AISLADOS"
    COMPONENTES = "COMPONENTES"
    DISPOSITIVOS = "DISPOSITIVOS"
    CONEXIONES = "CONEXIONES"
    VISUALIZAR = "VISUALIZAR"
    OPERATIVO = "OPERATIVO"
    ES_ESTADO = "ES_ESTADO"
    RUTA = "RUTA"
    Y = "Y"
    O = "O"
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    FAILURE = "FAILURE"
    FISICA = "FISICA"
    OPERATIVA = "OPERATIVA"
    ID = "ID"
    IP = "IP"
    SEQ = "SEQ"
    LPAREN = "("
    RPAREN = ")"
    COMMA = ","
    EOF = "EOF"


KEYWORDS = {
    token_type.value: token_type
    for token_type in TokenType
    if token_type
    not in {
        TokenType.ID,
        TokenType.IP,
        TokenType.SEQ,
        TokenType.LPAREN,
        TokenType.RPAREN,
        TokenType.COMMA,
        TokenType.EOF,
    }
}
PUNCTUATION = {
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ",": TokenType.COMMA,
}
_ATOM_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_."
)


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    lexeme: str
    position: int


class LexerError(Exception):
    """Raised when the input contains an invalid lexical unit."""

    def __init__(self, position: int, message: str, lexeme: str = "") -> None:
        self.position = position
        self.lexeme = lexeme
        super().__init__(f"posición {position}: {message}")


def _classify_atom(lexeme: str, position: int) -> TokenType:
    keyword = KEYWORDS.get(lexeme)
    if keyword is not None:
        return keyword
    if DEVICE_ID_PATTERN.fullmatch(lexeme) is not None:
        return TokenType.ID
    if IPV4_PATTERN.fullmatch(lexeme) is not None:
        if all(int(octet) <= 255 for octet in lexeme.split(".")):
            return TokenType.IP
        raise LexerError(position, f"IPv4 léxicamente inválida {lexeme!r}", lexeme)
    if HEALTH_EVENTS_PATTERN.fullmatch(lexeme) is not None:
        return TokenType.SEQ
    if "." in lexeme and all(character.isdigit() or character == "." for character in lexeme):
        raise LexerError(position, f"IPv4 léxicamente inválida {lexeme!r}", lexeme)

    for offset, character in enumerate(lexeme):
        if character not in _ATOM_CHARACTERS:
            raise LexerError(
                position + offset, f"carácter desconocido {character!r}", character
            )
    raise LexerError(position, f"token desconocido {lexeme!r}", lexeme)


def tokenize(source: str) -> list[Token]:
    """Consume the complete source and return immutable-positioned tokens."""
    if not isinstance(source, str):
        raise TypeError("source must be a string.")

    tokens: list[Token] = []
    position = 0
    while position < len(source):
        character = source[position]
        if character.isspace():
            position += 1
            continue
        punctuation = PUNCTUATION.get(character)
        if punctuation is not None:
            tokens.append(Token(punctuation, character, position))
            position += 1
            continue

        start = position
        while (
            position < len(source)
            and not source[position].isspace()
            and source[position] not in PUNCTUATION
        ):
            position += 1
        lexeme = source[start:position]
        tokens.append(Token(_classify_atom(lexeme, start), lexeme, start))

    tokens.append(Token(TokenType.EOF, "", len(source)))
    return tokens
