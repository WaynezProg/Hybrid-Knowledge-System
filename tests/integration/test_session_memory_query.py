from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.cli import app


@pytest.mark.integration
def test_session_memory_date_query_prefers_daily_source_over_graph_fixture(
    cli_runner,
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    daily_dir = docs / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-05-22.md").write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-22\n"
        "source_domain: session_memory\n"
        "generator: session2memory\n"
        "---\n"
        "# 2026-05-22\n\n"
        "- [activity] 完成 HKS session metadata propagation。 "
        "(workspace: hks, evidence: e000001, source: codex, session: s1, lines: 2-2)\n",
        encoding="utf-8",
    )
    (docs / "graph-fixture.md").write_text(
        "# Graph Fixture\n\n"
        "Vibe coding 影響錯誤 graph 測試資料。\n",
        encoding="utf-8",
    )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout

    result = cli_runner.invoke(
        app,
        ["query", "2026-05-22 vibe coding 影響什麼", "--writeback=no"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["trace"]["route"] == "wiki"
    assert payload["source"] == ["wiki"]
    assert "session metadata propagation" in payload["answer"]
    assert payload["evidence"][0]["source_relpath"] == "daily/2026-05-22.md"
    assert "Graph Fixture" not in payload["answer"]
