from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.cli import app
from hks.storage.vector import VectorStore


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
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "tools: [codex]\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-22\n\n"
        "## Entries\n"
        "- [activity] 完成 HKS session metadata propagation。 "
        "{workspace_id=hks memory_kind=activity tool=codex "
        "session_id=s1 evidence_id=e000001 lines=2-2}\n",
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


@pytest.mark.integration
def test_session2memory_entry_metadata_reaches_vector_chunks(
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
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "tools: [codex]\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-22\n\n"
        "## Entries\n"
        "- [activity] 完成 HKS session metadata propagation。 "
        "{workspace_id=hks memory_kind=activity tool=codex "
        "session_id=s1 evidence_id=e000001 lines=2-2}\n",
        encoding="utf-8",
    )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout

    hits = VectorStore().search("session metadata propagation", top_k=10)
    entry_hit = next(hit for hit in hits if "session metadata propagation" in hit.text)

    assert entry_hit.metadata["source_relpath"] == "daily/2026-05-22.md"
    assert entry_hit.metadata["workspace_id"] == "hks"
    assert entry_hit.metadata["memory_kind"] == "activity"
    assert entry_hit.metadata["tool"] == "codex"
    assert entry_hit.metadata["session_id"] == "s1"
    assert entry_hit.metadata["evidence_id"] == "e000001"
