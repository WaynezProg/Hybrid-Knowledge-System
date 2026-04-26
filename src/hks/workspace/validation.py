"""Validation helpers for workspace registry operations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hks.errors import ExitCode, KSError

WORKSPACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def validate_workspace_id(workspace_id: str) -> str:
    if not WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise KSError(
            "workspace id must match ^[a-z0-9][a-z0-9._-]{0,63}$",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return workspace_id


def resolve_workspace_root(ks_root: str | Path) -> Path:
    return Path(ks_root).expanduser().resolve(strict=False)


def validate_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, str | int | float | bool | None]:
    normalized: dict[str, str | int | float | bool | None] = {}
    for key, value in (metadata or {}).items():
        if not isinstance(key, str):
            raise KSError("metadata keys must be strings", exit_code=ExitCode.USAGE, code="USAGE")
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise KSError(
                "metadata values must be scalar JSON values",
                exit_code=ExitCode.USAGE,
                code="USAGE",
            )
        normalized[key] = value
    return normalized


def shell_export_command(ks_root: str) -> str:
    escaped = ks_root.replace("'", "'\"'\"'")
    return f"export KS_ROOT='{escaped}'"
