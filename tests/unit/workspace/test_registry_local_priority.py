"""Tests that registry_path prefers project-local .hks-runs/workspaces.json."""
from __future__ import annotations

from pathlib import Path

import pytest

from hks.workspace.registry import registry_path


def test_project_local_takes_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HKS_WORKSPACE_REGISTRY", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    local_dir = tmp_path / ".hks-runs"
    local_dir.mkdir()
    (local_dir / "workspaces.json").write_text("{}")

    result = registry_path()
    assert result == (local_dir / "workspaces.json").resolve()


def test_env_var_overrides_project_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "custom" / "workspaces.json"
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(env_path))
    monkeypatch.chdir(tmp_path)
    local_dir = tmp_path / ".hks-runs"
    local_dir.mkdir()
    (local_dir / "workspaces.json").write_text("{}")

    result = registry_path()
    assert result == env_path.resolve()


def test_fallback_to_xdg_when_no_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HKS_WORKSPACE_REGISTRY", raising=False)
    xdg = tmp_path / "xdg_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.chdir(tmp_path)
    # No .hks-runs directory

    result = registry_path()
    assert result == (xdg / "hks" / "workspaces.json").resolve()
