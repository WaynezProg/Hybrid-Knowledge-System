"""Integration tests for --workspace-route auto-routing ingest."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.workspace.registry import load_registry

runner = CliRunner()


def test_workspace_route_splits_by_frontmatter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"

    source_dir = tmp_path / "session-export"
    source_dir.mkdir()
    (source_dir / "ws-a.md").write_text(
        "---\nworkspace_id: ws-a\nhks_type: session_daily\n---\n# A\nContent A\n"
    )
    (source_dir / "ws-b.md").write_text(
        "---\nworkspace_id: ws-b\nhks_type: session_daily\n---\n# B\nContent B\n"
    )
    (source_dir / "no-ws.md").write_text("# No workspace\nPlain content\n")

    result = runner.invoke(
        app,
        [
            "ingest",
            str(source_dir),
            "--workspace-route",
            "--registry-path",
            str(reg_path),
        ],
    )

    assert result.exit_code == 0

    registry = load_registry(reg_path)
    assert "ws-a" in registry.workspaces
    assert "ws-b" in registry.workspaces

    ws_a_root = Path(registry.workspaces["ws-a"].ks_root)
    ws_b_root = Path(registry.workspaces["ws-b"].ks_root)
    assert (ws_a_root / "manifest.json").exists()
    assert (ws_b_root / "manifest.json").exists()


def test_workspace_route_and_workspace_flag_mutually_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.md").write_text("# A\n")

    result = runner.invoke(
        app,
        ["ingest", str(source_dir), "-w", "foo", "--workspace-route"],
    )

    assert result.exit_code != 0
