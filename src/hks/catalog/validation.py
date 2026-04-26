"""Validation helpers for source catalog commands."""

from __future__ import annotations

from hks.core.manifest import SUPPORTED_SUFFIXES, SourceFormat
from hks.errors import ExitCode, KSError


def normalize_format(value: str | None) -> SourceFormat | None:
    if value is None:
        return None
    normalized = value.lower().strip()
    if normalized not in SUPPORTED_SUFFIXES:
        raise KSError(
            f"unsupported source format filter: {value}",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return normalized  # type: ignore[return-value]


def validate_relpath(relpath: str) -> str:
    if not relpath or relpath.startswith("/") or "\x00" in relpath:
        raise KSError(
            "source relpath must be a manifest-relative path",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    parts = relpath.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise KSError(
            "source relpath must not contain empty, current, or parent segments",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return relpath


def validate_pagination(limit: int | None, offset: int | None) -> tuple[int | None, int]:
    if limit is not None and limit < 1:
        raise KSError("limit must be >= 1", exit_code=ExitCode.USAGE, code="USAGE")
    normalized_offset = offset or 0
    if normalized_offset < 0:
        raise KSError("offset must be >= 0", exit_code=ExitCode.USAGE, code="USAGE")
    return limit, normalized_offset

