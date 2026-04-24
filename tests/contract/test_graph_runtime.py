from __future__ import annotations

import json

import pytest

from hks.cli import app


@pytest.mark.contract
def test_runtime_outputs_can_emit_graph(cli_runner, working_docs, tmp_ks_root) -> None:
    ingest_result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert ingest_result.exit_code == 0

    query_result = cli_runner.invoke(app, ["query", "A 專案延遲影響哪些系統", "--writeback=no"])
    assert query_result.exit_code == 0

    lint_result = cli_runner.invoke(app, ["lint"])
    assert lint_result.exit_code == 0

    ingest_payload = json.loads(ingest_result.stdout)
    relation_payload = json.loads(query_result.stdout)
    lint_payload = json.loads(lint_result.stdout)

    assert ingest_payload["trace"]["steps"][0]["kind"] == "ingest_summary"
    assert relation_payload["trace"]["route"] == "graph"
    assert relation_payload["source"] == ["graph"]
    assert lint_payload["trace"]["route"] == "wiki"
    assert (tmp_ks_root / "graph" / "graph.json").exists()


@pytest.mark.contract
def test_src_contains_graph_runtime_paths() -> None:
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    graph_sources = sorted(
        path.relative_to(project_root).as_posix()
        for path in (project_root / "src" / "hks").rglob("*.py")
        if "/graph/" in path.as_posix()
    )
    assert graph_sources != []
