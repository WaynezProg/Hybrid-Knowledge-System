"""Shared error contracts for the CLI."""

from __future__ import annotations

from collections.abc import Sequence
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hks.core.schema import QueryResponse


class ExitCode(IntEnum):
    """BSD sysexits subset for the public CLI contract."""

    OK = 0
    GENERAL = 1
    USAGE = 2
    DATAERR = 65
    NOINPUT = 66


class KSError(Exception):
    """Base exception that carries stderr and JSON response metadata."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: ExitCode = ExitCode.GENERAL,
        code: str | None = None,
        route: str = "wiki",
        level: str = "error",
        details: Sequence[str] | None = None,
        hint: str | None = None,
        response: QueryResponse | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.code = code or exit_code.name
        self.route = route
        self.level = level
        self.details = list(details or [])
        self.hint = hint
        self.response = response

    def stderr_message(self, command: str) -> str:
        lines = [f"[ks:{command}] {self.level}: {self.message}"]
        lines.extend(f"  {detail}" for detail in self.details)
        if self.hint:
            lines.append(f"  hint: {self.hint}")
        return "\n".join(lines)


class FeatureNotImplementedError(KSError):
    """Raised by commands that are present in the contract but not built yet."""

    def __init__(self, command: str, detail: str) -> None:
        super().__init__(
            f"{command} 尚未實作",
            exit_code=ExitCode.GENERAL,
            code="NOT_IMPLEMENTED",
            details=[detail],
        )
