"""Agent-profile configuration for MCP/HTTP adapters."""

from __future__ import annotations

import os
from pathlib import Path

from hks.core.config import (
    ENV_AGENT_PROFILE,
    ENV_KS_ROOT_BASE,
    ENV_SESSION2MEMORY_EXPORT_ROOT,
)
from hks.errors import ExitCode, KSError

AGENT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "hks_workspace_query",
        "hks_workspace_ingest_session_memory",
        "hks_workspace_show",
        "hks_workspace_list",
        "hks_session_memory_summary",
        "hks_source_list",
        "hks_source_show",
    }
)

_AGENT_PROFILE_VALUES = frozenset({"1", "true", "yes", "on"})


def is_agent_profile() -> bool:
    return os.environ.get(ENV_AGENT_PROFILE, "").strip().lower() in _AGENT_PROFILE_VALUES


def require_export_root() -> Path:
    configured = os.environ.get(ENV_SESSION2MEMORY_EXPORT_ROOT, "").strip()
    if not configured:
        raise KSError(
            f"{ENV_SESSION2MEMORY_EXPORT_ROOT} is required for agent-profile ingest",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return Path(configured).expanduser().resolve(strict=False)


def require_ks_root_base() -> Path:
    configured = os.environ.get(ENV_KS_ROOT_BASE, "").strip()
    if not configured:
        raise KSError(
            f"{ENV_KS_ROOT_BASE} is required for agent-profile workspaces",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return Path(configured).expanduser().resolve(strict=False)


def ks_root_for_workspace(workspace_id: str) -> Path:
    return (require_ks_root_base() / workspace_id).resolve(strict=False)
