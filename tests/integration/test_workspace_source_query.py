"""Integration tests for workspace-scoped source and query commands."""
from __future__ import annotations

from pathlib import Path

import pytest

from typer.testing import CliRunner

from hks.cli import app
from hks.workspace.service import register_workspace

runner = CliRunner()


def _setup_workspace(tmp_path: Path, wid: str) -> Path:
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"
    ws_root = tmp_path / ".hks-runs" / wid / "ks"
    ws_root.mkdir(parents=True)
    register_workspace(wid, ks_root=ws_root, registry_path_value=reg_path)

    source_dir = tmp_path / f"sources-{wid}"
    source_dir.mkdir()
    (source_dir / "doc.md").write_text(f"# {wid}\n\nContent for {wid}")

    result = runner.invoke(
        app,
        ["ingest", str(source_dir), "-w", wid, "--registry-path", str(reg_path)],
    )
    assert result.exit_code == 0
    return reg_path


def test_source_list_with_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = _setup_workspace(tmp_path, "ws-alpha")
    _setup_workspace(tmp_path, "ws-beta")

    result = runner.invoke(
        app,
        ["source", "list", "-w", "ws-alpha", "--registry-path", str(reg_path)],
    )
    assert result.exit_code == 0
    assert "ws-alpha" in result.stdout or "doc.md" in result.stdout


def test_query_with_workspace_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = _setup_workspace(tmp_path, "ws-gamma")

    result = runner.invoke(
        app,
        ["query", "what is ws-gamma", "-w", "ws-gamma", "--registry-path", str(reg_path)],
    )
    assert result.exit_code == 0
