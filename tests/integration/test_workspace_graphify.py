"""Integration tests for workspace-scoped graphify build."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.workspace.service import register_workspace

runner = CliRunner()


def test_graphify_build_with_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"
    ws_root = tmp_path / ".hks-runs" / "test-gfx" / "ks"
    ws_root.mkdir(parents=True)
    register_workspace("test-gfx", ks_root=ws_root, registry_path_value=reg_path)

    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "concept.md").write_text(
        "# Concepts\n\nAPI latency 導致 deployment delay\n"
    )

    runner.invoke(
        app,
        ["ingest", str(source_dir), "-w", "test-gfx", "--registry-path", str(reg_path)],
    )

    result = runner.invoke(
        app,
        [
            "graphify",
            "build",
            "--mode",
            "store",
            "-w",
            "test-gfx",
            "--registry-path",
            str(reg_path),
        ],
    )

    assert result.exit_code == 0
    assert (ws_root / "graphify").exists()
