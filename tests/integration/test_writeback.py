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


def _wiki_page_count(tmp_ks_root) -> int:
    return len(list((tmp_ks_root / "wiki" / "pages").glob("*.md")))


def _queue_files(tmp_ks_root) -> list:
    return sorted((tmp_ks_root / "writeback" / "queue").glob("*.json"))


def _log_text(tmp_ks_root) -> str:
    return (tmp_ks_root / "wiki" / "log.md").read_text(encoding="utf-8")


def _writeback_step(payload: dict[str, object]) -> dict[str, object]:
    return next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_ask_yes_enqueues(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        query_command,
        "decide",
        lambda flag, *, assessment=None, confidence=None, is_tty=False, prompt=None: Decision(
            action="enqueue", status="enqueued"
        ),
    )
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    step = _writeback_step(payload)
    assert step["detail"]["status"] == "enqueued"
    assert step["detail"]["id"]
    assert len(_queue_files(tmp_ks_root)) == 1
    assert _wiki_page_count(tmp_ks_root) == before_pages


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
            action="skip", status="declined"
        ),
    )
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert _queue_files(tmp_ks_root) == []
    assert _wiki_page_count(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_auto_declines_wiki_route_when_explicit(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    before_pages = _wiki_page_count(tmp_ks_root)
    before_log = _log_text(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=auto"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["source"] == ["wiki"]
    assert payload["writeback_eligible"] is False
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "skipped-ineligible"
    assert _queue_files(tmp_ks_root) == []
    assert _wiki_page_count(tmp_ks_root) == before_pages
    assert _log_text(tmp_ks_root) == before_log


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_default_is_no(cli_runner, ingested_for_writeback, tmp_ks_root) -> None:
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert _queue_files(tmp_ks_root) == []
    assert _wiki_page_count(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_ask_non_tty_skips_queue(cli_runner, ingested_for_writeback, tmp_ks_root) -> None:
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "skip-non-tty"
    assert _queue_files(tmp_ks_root) == []
    assert _wiki_page_count(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_yes_enqueues_without_wiki_page_or_forced_event(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    writeback_step = _writeback_step(payload)
    assert writeback_step["detail"]["status"] == "enqueued"
    assert writeback_step["detail"]["id"]
    assert writeback_step["detail"]["path"]
    queue_files = _queue_files(tmp_ks_root)
    assert len(queue_files) == 1
    item = json.loads(queue_files[0].read_text(encoding="utf-8"))
    assert item["question"] == "summary Atlas"
    assert item["answer"] == payload["answer"]
    assert item["route"] == payload["trace"]["route"]
    assert item["source"] == payload["source"]
    assert item["evidence"] == payload["evidence"]
    assert item["retrieval_score"] == payload["retrieval_score"]
    assert item["writeback_eligible"] == payload["writeback_eligible"]
    assert item["reasons"]
    events_path = tmp_ks_root / "coordination" / "events.jsonl"
    if events_path.exists():
        assert "forced_writeback" not in events_path.read_text(encoding="utf-8")
    assert "writeback | enqueued" in _log_text(tmp_ks_root)
    assert _wiki_page_count(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_no_overrides_and_skips_enqueue(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert _queue_files(tmp_ks_root) == []
    assert _wiki_page_count(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_yes_dedupes_same_query(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    first = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])
    after_first_log = _log_text(tmp_ks_root)
    second = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    assert _writeback_step(payload)["detail"]["status"] == "enqueued-deduped"
    assert len(_queue_files(tmp_ks_root)) == 1
    assert _log_text(tmp_ks_root) == after_first_log


@pytest.mark.integration
def test_query_response_includes_015_confidence_fields(
    cli_runner, ingested_for_writeback
) -> None:
    result = cli_runner.invoke(app, ["query", "Project Atlas summary", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "retrieval_score" in payload
    assert "calibrated_confidence" not in payload
    assert "writeback_eligible" in payload
    assert isinstance(payload["retrieval_score"], (int, float))
    assert isinstance(payload["confidence"], (int, float))
    assert isinstance(payload["writeback_eligible"], bool)
    assert payload["confidence"] == max(0.0, min(float(payload["retrieval_score"]), 1.0))


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
def test_writeback_yes_no_hit_skips_queue(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    before_pages = _wiki_page_count(tmp_ks_root)

    result = cli_runner.invoke(app, ["query", "zzzz nonexistent topic", "--writeback=yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["source"] == []
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "skip-no-source"
    assert _queue_files(tmp_ks_root) == []
    assert _wiki_page_count(tmp_ks_root) == before_pages
