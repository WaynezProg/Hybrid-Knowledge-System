"""Atomic persistence for local workspace registry."""

from __future__ import annotations

import json
import os
from pathlib import Path

from hks.core.config import config_value
from hks.core.manifest import atomic_write, utc_now_iso
from hks.errors import ExitCode, KSError
from hks.workspace.models import WorkspaceRegistry

ENV_REGISTRY = "HKS_WORKSPACE_REGISTRY"
SCHEMA_VERSION = 1


def registry_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path).expanduser().resolve(strict=False)
    env_path = config_value(ENV_REGISTRY)
    if env_path:
        return Path(env_path).expanduser().resolve(strict=False)
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return (Path(xdg_config).expanduser() / "hks" / "workspaces.json").resolve(strict=False)
    return (Path.home() / ".config" / "hks" / "workspaces.json").resolve(strict=False)


def empty_registry() -> WorkspaceRegistry:
    return WorkspaceRegistry(schema_version=SCHEMA_VERSION, updated_at=utc_now_iso(), workspaces={})


def load_registry(path: str | Path | None = None) -> WorkspaceRegistry:
    resolved = registry_path(path)
    if not resolved.exists():
        return empty_registry()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("registry root must be an object")
        registry = WorkspaceRegistry.from_dict(payload)
    except Exception as exc:
        raise KSError(
            "workspace registry 無法讀取",
            exit_code=ExitCode.DATAERR,
            code="WORKSPACE_REGISTRY_CORRUPT",
            details=[f"{resolved}: {exc}"],
        ) from exc
    if registry.schema_version != SCHEMA_VERSION:
        raise KSError(
            "workspace registry schema version 不支援",
            exit_code=ExitCode.DATAERR,
            code="WORKSPACE_REGISTRY_INVALID",
            details=[f"{resolved}: schema_version={registry.schema_version}"],
        )
    return registry


def save_registry(registry: WorkspaceRegistry, path: str | Path | None = None) -> Path:
    resolved = registry_path(path)
    payload = WorkspaceRegistry(
        schema_version=SCHEMA_VERSION,
        updated_at=utc_now_iso(),
        workspaces=registry.workspaces,
    ).to_dict()
    atomic_write(resolved, json.dumps(payload, ensure_ascii=False, indent=2))
    return resolved
