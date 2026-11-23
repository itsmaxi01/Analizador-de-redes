import pytest

from lexer import LexerError, TokenType, tokenize


def test_tokenize_preserves_types_lexemes_and_positions():
    tokens = tokenize(" EVENTO(Switch1, RRT) ")
    assert [(token.type, token.lexeme, token.position) for token in tokens] == [
        (TokenType.EVENTO, "EVENTO", 1),
        (TokenType.LPAREN, "(", 7),
        (TokenType.ID, "Switch1", 8),
        (TokenType.COMMA, ",", 15),
        (TokenType.SEQ, "RRT", 17),
        (TokenType.RPAREN, ")", 20),
        (TokenType.EOF, "", 22),
    ]


@pytest.mark.parametrize("ip", ["8.8.8.8", "192.168.1.0", "0.0.0.0", "255.255.255.255"])
def test_lexically_valid_ipv4_does_not_apply_domain_ranges(ip):
    assert tokenize(ip)[0].type is TokenType.IP


@pytest.mark.parametrize("source", ["256.1.1.1", "192.168.01.1", "1.2.3", "1.2.3.4.5"])
def test_structurally_invalid_ipv4(source):
    with pytest.raises(LexerError, match="IPv4 léxicamente inválida"):
        tokenize(source)


@pytest.mark.parametrize(
    "source, expected",
    [("PC999", TokenType.ID), ("RRTT", TokenType.SEQ), ("OPERATIVA", TokenType.OPERATIVA)],
)
def test_priority_between_id_sequence_and_keywords(source, expected):
    assert tokenize(source)[0].type is expected


@pytest.mark.parametrize("source", ["PC0", "Router01", "pc1", "RRTX", "DESCONOCIDO"])
def test_invalid_atoms_are_not_partially_accepted(source):
    with pytest.raises(LexerError, match="posición 0"):
        tokenize(source)


def test_unknown_character_reports_its_exact_position():
    with pytest.raises(LexerError, match=r"posición 14: carácter desconocido '@'"):
        tokenize("OPERATIVO(PC1)@")
