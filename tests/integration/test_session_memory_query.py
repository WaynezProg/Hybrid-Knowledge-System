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


@pytest.mark.integration
def test_workspace_status_query_prefers_vector_over_wiki(
    cli_runner,
    tmp_path: Path,
) -> None:
    """Workspace status query should use workspace-matched vector hits,
    not generic wiki date pages."""
    docs = tmp_path / "docs"
    daily_dir = docs / "daily"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-21.md").write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-21\n"
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "tools: [codex]\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-21\n\n"
        "## Entries\n"
        "- [verification] pytest 4 passed "
        "{workspace_id=social-bank-check-d61a68f0 memory_kind=verification "
        "tool=codex session_id=s1 evidence_id=e000013 lines=751-751}\n"
        "- [verification] pytest 8 passed "
        "{workspace_id=social-bank-check-d61a68f0 memory_kind=verification "
        "tool=codex session_id=s1 evidence_id=e000014 lines=1701-1701}\n"
        "- [activity] HKS metadata propagation "
        "{workspace_id=hks-81c05951 memory_kind=activity "
        "tool=codex session_id=s2 evidence_id=e000001 lines=2-2}\n",
        encoding="utf-8",
    )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout

    result = cli_runner.invoke(
        app,
        ["query", "social-bank-check 最後處理到哪", "--writeback=no"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    assert "social-bank-check" in payload["answer"]
    assert "HKS metadata propagation" not in payload["answer"]

    has_workspace_step = any(
        step.get("kind") == "workspace_status_synthesis"
        for step in payload["trace"]["steps"]
    )
    assert has_workspace_step, "should have workspace_status_synthesis trace step"


@pytest.mark.integration
def test_workspace_status_query_with_date_filters_vector_entries(
    cli_runner,
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    daily_dir = docs / "daily"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-20.md").write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-20\n"
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-20\n\n"
        "## Entries\n"
        "- [activity] old status entry "
        "{workspace_id=social-bank-check-d61a68f0 memory_kind=activity "
        "tool=codex session_id=s1 evidence_id=e000001 lines=10-10}\n",
        encoding="utf-8",
    )
    (daily_dir / "2026-05-21.md").write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-21\n"
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-21\n\n"
        "## Entries\n"
        "- [activity] latest status entry "
        "{workspace_id=social-bank-check-d61a68f0 memory_kind=activity "
        "tool=codex session_id=s2 evidence_id=e000002 lines=20-20}\n",
        encoding="utf-8",
    )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout

    result = cli_runner.invoke(
        app,
        ["query", "2026/5/21 social-bank-check 狀態", "--writeback=no"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "latest status entry" in payload["answer"]
    assert "old status entry" not in payload["answer"]


@pytest.mark.integration
def test_workspace_status_auto_writeback_stays_ineligible(
    cli_runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = tmp_path / "docs"
    daily_dir = docs / "daily"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-21.md").write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-21\n"
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-21\n\n"
        "## Entries\n"
        "- [verification] pytest 819 passed "
        "{workspace_id=social-bank-check-d61a68f0 memory_kind=verification "
        "tool=codex session_id=s1 evidence_id=e000013 lines=751-751}\n",
        encoding="utf-8",
    )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout
    monkeypatch.setenv("HKS_WRITEBACK_AUTO_THRESHOLD", "0")

    result = cli_runner.invoke(
        app,
        ["query", "social-bank-check 最後處理到哪", "--writeback=auto"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    assert payload["writeback_eligible"] is False
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "auto-skipped-ineligible"


@pytest.mark.integration
def test_workspace_query_without_status_keyword_still_filters(
    cli_runner,
    tmp_path: Path,
) -> None:
    """Workspace query without status keywords should still prefer
    workspace-matched candidates over generic wiki."""
    docs = tmp_path / "docs"
    daily_dir = docs / "daily"
    daily_dir.mkdir(parents=True)

    (daily_dir / "2026-05-21.md").write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-21\n"
        "generator: session2memory\n"
        "source_domain: coding_session\n"
        "schema_version: 1\n"
        "---\n"
        "# 2026-05-21\n\n"
        "## Entries\n"
        "- [activity] social-bank compliance check completed stage 3 "
        "{workspace_id=social-bank-check-d61a68f0 memory_kind=activity "
        "tool=codex session_id=s1 evidence_id=e000001 lines=10-10}\n"
        "- [activity] HKS vector retrieval refactored "
        "{workspace_id=hks-81c05951 memory_kind=activity "
        "tool=codex session_id=s2 evidence_id=e000002 lines=20-20}\n",
        encoding="utf-8",
    )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout

    result = cli_runner.invoke(
        app,
        ["query", "social-bank-check 做了什麼", "--writeback=no"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    assert "HKS vector retrieval" not in payload["answer"]


@pytest.mark.integration
def test_session_memory_date_range_query_synthesizes_three_days(
    cli_runner,
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    daily_dir = docs / "daily"
    daily_dir.mkdir(parents=True)

    fixtures = {
        "2026-05-25": "project-alpha step one done",
        "2026-05-26": "project-alpha step two done",
        "2026-05-27": "project-beta step three done",
    }
    for day, snippet in fixtures.items():
        (daily_dir / f"{day}.md").write_text(
            "---\n"
            f"hks_type: session_daily\n"
            f"date: {day}\n"
            "generator: session2memory\n"
            "source_domain: coding_session\n"
            "schema_version: 1\n"
            "---\n"
            f"# {day}\n\n"
            "## Entries\n"
            f"- [activity] {snippet} "
            "{workspace_id=demo-project memory_kind=activity tool=codex "
            "session_id=s1 evidence_id=e000001 lines=1-1}\n",
            encoding="utf-8",
        )

    ingest = cli_runner.invoke(app, ["ingest", str(docs)])
    assert ingest.exit_code == 0, ingest.stdout

    result = cli_runner.invoke(
        app,
        ["query", "25~27 之間 project 做了哪些事情", "--writeback=no"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    for day in fixtures:
        assert day in payload["answer"]
        assert fixtures[day] in payload["answer"]

    evidence_paths = {item["source_relpath"] for item in payload["evidence"]}
    assert evidence_paths >= {
        "daily/2026-05-25.md",
        "daily/2026-05-26.md",
        "daily/2026-05-27.md",
    }

    assert any(
        step.get("kind") == "date_range_synthesis"
        for step in payload["trace"]["steps"]
    )
