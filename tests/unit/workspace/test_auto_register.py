"""Tests for workspace auto-registration with default KS_ROOT."""
from __future__ import annotations

from pathlib import Path

import pytest

from hks.workspace.registry import default_ks_root, load_registry
from hks.workspace.service import ensure_workspace


def test_default_ks_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = default_ks_root("social-bank-check")
    assert result == (tmp_path / ".hks-runs" / "social-bank-check" / "ks").resolve()


def test_ensure_workspace_creates_new(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"

    record = ensure_workspace("my-workspace", registry_path_value=reg_path)

    assert record.id == "my-workspace"
    assert record.ks_root == (tmp_path / ".hks-runs" / "my-workspace" / "ks").resolve().as_posix()
    assert Path(record.ks_root).exists()

    registry = load_registry(reg_path)
    assert "my-workspace" in registry.workspaces


def test_ensure_workspace_returns_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"

    first = ensure_workspace("my-workspace", registry_path_value=reg_path)
    second = ensure_workspace("my-workspace", registry_path_value=reg_path)

    assert first.ks_root == second.ks_root
    assert first.created_at == second.created_at
