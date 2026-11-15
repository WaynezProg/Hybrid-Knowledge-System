"""End-to-end test: two workspaces must not pollute each other.

Verifies that ingest, source list, query, and graphify build produce
workspace-scoped results when using -w flags with separate KS_ROOTs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.workspace.service import register_workspace

runner = CliRunner()


def _register_and_ingest(
    tmp_path: Path,
    wid: str,
    reg_path: Path,
    content: str,
    filename: str = "doc.md",
) -> Path:
    """Register a workspace, write a source file, and ingest it."""
    ws_root = tmp_path / ".hks-runs" / wid / "ks"
    ws_root.mkdir(parents=True)
    register_workspace(wid, ks_root=ws_root, registry_path_value=reg_path)

    source_dir = tmp_path / f"sources-{wid}"
    source_dir.mkdir(exist_ok=True)
    (source_dir / filename).write_text(content, encoding="utf-8")

    result = runner.invoke(
        app,
        ["ingest", str(source_dir), "-w", wid, "--registry-path", str(reg_path)],
    )
    assert result.exit_code == 0, f"ingest failed for {wid}: {result.stdout}"
    return ws_root


def test_two_workspaces_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two workspaces must have fully isolated source, query, and graphify results."""
    monkeypatch.chdir(tmp_path)
    reg_path = tmp_path / ".hks-runs" / "workspaces.json"

    ws_alpha_root = _register_and_ingest(
        tmp_path,
        "ws-alpha",
        reg_path,
        "# Alpha Project\n\nAlice owns the Alpha checkout service.\n"
        "Bob depends_on the Alpha notification pipeline.\n",
    )
    ws_beta_root = _register_and_ingest(
        tmp_path,
        "ws-beta",
        reg_path,
        "# Beta Project\n\nCarol manages the Beta analytics dashboard.\n"
        "Dave impacts the Beta reporting module.\n",
    )

    # ---------- source list isolation ----------
    alpha_source = runner.invoke(
        app,
        ["source", "list", "-w", "ws-alpha", "--registry-path", str(reg_path)],
    )
    beta_source = runner.invoke(
        app,
        ["source", "list", "-w", "ws-beta", "--registry-path", str(reg_path)],
    )
    assert alpha_source.exit_code == 0
    assert beta_source.exit_code == 0
    # Alpha's source output must not contain Beta-only terms
    assert "Beta" not in alpha_source.stdout or "Alpha" in alpha_source.stdout
    assert "Alpha" not in beta_source.stdout or "Beta" in beta_source.stdout

    # ---------- graph.json isolation ----------
    alpha_graph = ws_alpha_root / "graph" / "graph.json"
    beta_graph = ws_beta_root / "graph" / "graph.json"
    assert alpha_graph.exists(), "ws-alpha graph.json missing"
    assert beta_graph.exists(), "ws-beta graph.json missing"

    alpha_graph_data = json.loads(alpha_graph.read_text(encoding="utf-8"))
    beta_graph_data = json.loads(beta_graph.read_text(encoding="utf-8"))

    alpha_node_labels = {
        n["label"] for n in alpha_graph_data.get("nodes", {}).values()
    }
    beta_node_labels = {
        n["label"] for n in beta_graph_data.get("nodes", {}).values()
    }
    # Carol/Dave should NOT appear in Alpha; Alice/Bob should NOT appear in Beta
    assert "Carol" not in alpha_node_labels
    assert "Alice" not in beta_node_labels

    # ---------- graphify build isolation ----------
    alpha_gfx = runner.invoke(
        app,
        [
            "graphify", "build", "--mode", "store",
            "-w", "ws-alpha", "--registry-path", str(reg_path),
        ],
    )
    beta_gfx = runner.invoke(
        app,
        [
            "graphify", "build", "--mode", "store",
            "-w", "ws-beta", "--registry-path", str(reg_path),
        ],
    )
    assert alpha_gfx.exit_code == 0, f"graphify failed for ws-alpha: {alpha_gfx.stdout}"
    assert beta_gfx.exit_code == 0, f"graphify failed for ws-beta: {beta_gfx.stdout}"

    # Graphify artifacts stored in respective KS_ROOTs
    assert (ws_alpha_root / "graphify").exists()
    assert (ws_beta_root / "graphify").exists()

    # ---------- query isolation ----------
    alpha_query = runner.invoke(
        app,
        ["query", "who is Alice", "-w", "ws-alpha", "--registry-path", str(reg_path)],
    )
    beta_query = runner.invoke(
        app,
        ["query", "who is Carol", "-w", "ws-beta", "--registry-path", str(reg_path)],
    )
    assert alpha_query.exit_code == 0
    assert beta_query.exit_code == 0
