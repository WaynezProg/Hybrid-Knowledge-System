"""Integration tests for workspace-scoped ingest."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app

runner = CliRunner()


def test_ingest_with_workspace_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"
    ws_root = tmp_path / ".hks-runs" / "test-ws" / "ks"
    ws_root.mkdir(parents=True)

    from hks.workspace.service import register_workspace

    register_workspace("test-ws", ks_root=ws_root, registry_path_value=reg_path)

    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "hello.md").write_text("# Hello\n\nTest content here.")

    result = runner.invoke(
        app,
        [
            "ingest",
            str(source_dir),
            "-w",
            "test-ws",
            "--registry-path",
            str(reg_path),
        ],
    )

    assert result.exit_code == 0
    assert (ws_root / "manifest.json").exists()
    assert not (tmp_path / "ks" / "manifest.json").exists()
