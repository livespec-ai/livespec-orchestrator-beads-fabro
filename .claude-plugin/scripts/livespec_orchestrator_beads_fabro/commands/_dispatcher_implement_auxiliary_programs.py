"""Materialize the non-commit implement-workflow programs into every sandbox."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = [
    "GREEN_SCOPE_PROGRAM_FILENAME",
    "RESET_TEST_WRONG_PROGRAM_FILENAME",
    "green_token_scope_program_source",
    "reset_test_wrong_program_source",
]

RESET_TEST_WRONG_PROGRAM_FILENAME = "livespec-reset-test-wrong-to-dispatch-base.sh"
GREEN_SCOPE_PROGRAM_FILENAME = "livespec-green-token-scope.sh"
_RESET_TEST_WRONG_SOURCE_FILENAME = "_dispatcher_reset_test_wrong_program.sh"
_GREEN_SCOPE_SOURCE_FILENAME = "_dispatcher_green_token_scope_program.sh"


def _program_source(*, filename: str) -> str:
    """Read a shipped workflow program rather than target-repository tooling."""
    return Path(__file__).with_name(filename).read_text(encoding="utf-8")


def reset_test_wrong_program_source() -> str:
    """Return the program that returns a test-wrong lap to the dispatch base."""
    return _program_source(filename=_RESET_TEST_WRONG_SOURCE_FILENAME)


def green_token_scope_program_source() -> str:
    """Return the token-scope adapter used by the janitor's reuse path."""
    return _program_source(filename=_GREEN_SCOPE_SOURCE_FILENAME)
