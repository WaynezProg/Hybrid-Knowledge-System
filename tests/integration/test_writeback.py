from __future__ import annotations

import json

import pytest

import hks.commands.query as query_command
from hks.cli import app
from hks.writeback.gate import Decision


@pytest.fixture()
def ingested_for_writeback(cli_runner, working_docs):
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0
    return working_docs


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_ask_yes_commits(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        query_command,
        "decide",
        lambda flag, *, assessment=None, confidence=None, is_tty=False, prompt=None: Decision(
            action="commit", status="committed"
        ),
    )

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(step["kind"] == "writeback" for step in payload["trace"]["steps"])
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 11


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_ask_no_declines(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        query_command,
        "decide",
        lambda flag, *, assessment=None, confidence=None, is_tty=False, prompt=None: Decision(
            action="decline", status="declined"
        ),
    )

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_auto_declines_wiki_route_by_default(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["source"] == ["wiki"]
    assert payload["writeback_eligible"] is False
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "auto-skipped-ineligible"
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_yes_overrides_non_tty(cli_runner, ingested_for_writeback, tmp_ks_root) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    writeback_step = next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")
    assert writeback_step["detail"]["status"] == "forced-committed"
    assert writeback_step["detail"].get("forced") is True
    events_path = tmp_ks_root / "coordination" / "events.jsonl"
    assert "forced_writeback" in events_path.read_text(encoding="utf-8")
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 11


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_no_overrides_and_skips_commit(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10


@pytest.mark.integration
def test_query_response_includes_015_confidence_fields(
    cli_runner, ingested_for_writeback
) -> None:
    result = cli_runner.invoke(app, ["query", "Project Atlas summary", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "retrieval_score" in payload
    assert "calibrated_confidence" in payload
    assert "writeback_eligible" in payload
    assert isinstance(payload["retrieval_score"], (int, float))
    assert isinstance(payload["calibrated_confidence"], (int, float))
    assert isinstance(payload["writeback_eligible"], bool)
    assert payload["retrieval_score"] == payload["confidence"]


@pytest.mark.integration
def test_query_response_includes_rerank_trace_step(
    cli_runner, ingested_for_writeback
) -> None:
    result = cli_runner.invoke(app, ["query", "Project Atlas summary", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    rerank_steps = [step for step in payload["trace"]["steps"] if step["kind"] == "rerank"]
    assert len(rerank_steps) == 1
    assert "strategy" in rerank_steps[0]["detail"]


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_slug_collision_uses_suffix(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
) -> None:
    collision = tmp_ks_root / "wiki" / "pages" / "project-a-summary.md"
    collision.write_text(
        (
            "---\n"
            "slug: project-a-summary\n"
            "title: Project A Summary\n"
            "summary: existing\n"
            "source: <writeback>\n"
            "origin: writeback\n"
            "updated_at: 2026-04-24T00:00:00+00:00\n"
            "---\n\n"
            "# Project A Summary\n\n"
            "existing\n"
        ),
        encoding="utf-8",
    )

    result = cli_runner.invoke(app, ["query", "Project A summary", "--writeback=yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    writeback_step = next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")
    assert writeback_step["detail"]["slug"] == "project-a-summary-2"
    page_text = (tmp_ks_root / "wiki" / "pages" / "project-a-summary-2.md").read_text(
        encoding="utf-8"
    )
    assert "## Related" in page_text
