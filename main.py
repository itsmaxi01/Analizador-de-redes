"""Minimal interactive CLI for the Network Graph Analyzer."""

from __future__ import annotations

from pprint import pformat
from typing import Callable

from core.domain import DomainError
from core.loader import LoaderError
from core.session import NetworkSession, NoNetworkLoadedError
from language.evaluator import SemanticError, execute
from language.lexer import LexerError
from language.parser import ParserError


KNOWN_ERRORS = (
    LexerError,
    ParserError,
    SemanticError,
    DomainError,
    LoaderError,
    NoNetworkLoadedError,
    ValueError,
)


def run_cli(
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
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

        output_func(pformat(result, sort_dicts=False))


if __name__ == "__main__":
    run_cli()
