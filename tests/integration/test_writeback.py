from __future__ import annotations

import json

import pytest

import hks.commands.query as query_command
from hks.cli import app
from hks.core.paths import runtime_paths
from hks.storage.wiki import WikiStore
from hks.writeback.gate import Decision
from hks.writeback.queue import WritebackQueueItem, build_item, enqueue


@pytest.fixture()
def ingested_for_writeback(cli_runner, working_docs):
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0
    return working_docs


def _wiki_page_count(tmp_ks_root) -> int:
    return len(list((tmp_ks_root / "wiki" / "pages").glob("*.md")))


def _wiki_page_snapshot(tmp_ks_root) -> dict[str, bytes]:
    pages_dir = tmp_ks_root / "wiki" / "pages"
    return {
        path.name: path.read_bytes()
        for path in sorted(pages_dir.glob("*.md"))
    }


def _queue_files(tmp_ks_root) -> list:
    return sorted((tmp_ks_root / "writeback" / "queue").glob("*.json"))


def _archive_files(tmp_ks_root) -> list:
    return sorted((tmp_ks_root / "writeback" / "archive").glob("*.json"))


def _log_text(tmp_ks_root) -> str:
    return (tmp_ks_root / "wiki" / "log.md").read_text(encoding="utf-8")


def _writeback_step(payload: dict[str, object]) -> dict[str, object]:
    return next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")


def _json(path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    before_pages = _wiki_page_snapshot(tmp_ks_root)

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
    assert _wiki_page_snapshot(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_approve_promotes_queue_item_to_evidence_backed_wiki_page(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    query_result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])
    assert query_result.exit_code == 0
    query_payload = json.loads(query_result.stdout)
    query_step = _writeback_step(query_payload)
    item_id = str(query_step["detail"]["id"])
    queue_files = _queue_files(tmp_ks_root)
    assert len(queue_files) == 1

    approve_result = cli_runner.invoke(app, ["writeback", "approve", item_id])

    assert approve_result.exit_code == 0
    approve_payload = json.loads(approve_result.stdout)
    approve_step = _writeback_step(approve_payload)
    archive_files = _archive_files(tmp_ks_root)
    assert _queue_files(tmp_ks_root) == []
    assert len(archive_files) == 1
    archived = _json(archive_files[0])
    assert archived["id"] == item_id
    assert archived["status"] == "approved"
    assert archived["slug"] == approve_step["detail"]["slug"]

    page = WikiStore(runtime_paths(tmp_ks_root)).load_page(str(archived["slug"]))
    assert page.origin == "writeback"
    assert page.source_relpath != "<writeback>"
    assert page.source_relpath == archived["evidence"][0]["source_relpath"]
    assert page.metadata["writeback_query"] == "summary Atlas"
    assert query_payload["answer"] in page.body
    assert "## 來源依據" in page.body
    assert archived["evidence"][0]["quote"] in page.body
    assert archived["evidence"][0]["source_relpath"] in page.body


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_reject_archives_queue_item_without_wiki_changes(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    before_pages = _wiki_page_snapshot(tmp_ks_root)
    query_result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])
    assert query_result.exit_code == 0
    item_id = str(_writeback_step(json.loads(query_result.stdout))["detail"]["id"])
    assert len(_queue_files(tmp_ks_root)) == 1

    reject_result = cli_runner.invoke(app, ["writeback", "reject", item_id])

    assert reject_result.exit_code == 0
    reject_payload = json.loads(reject_result.stdout)
    reject_step = _writeback_step(reject_payload)
    assert reject_step["detail"]["status"] == "rejected"
    archive_files = _archive_files(tmp_ks_root)
    assert _queue_files(tmp_ks_root) == []
    assert len(archive_files) == 1
    archived = _json(archive_files[0])
    assert archived["id"] == item_id
    assert archived["status"] == "rejected"
    assert _wiki_page_snapshot(tmp_ks_root) == before_pages


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_approve_invalid_evidence_keeps_pending_item_rejectable(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    paths = runtime_paths(tmp_ks_root)
    item = build_item(
        question="Synthetic writeback answer",
        answer="Synthetic answer should not be promoted.",
        route="wiki",
        source=["wiki"],
        evidence=[{"route": "wiki", "source_relpath": "<writeback>", "quote": "synthetic"}],
        retrieval_score=0.9,
        writeback_eligible=True,
    )
    enqueue(item, paths=paths)

    approve_result = cli_runner.invoke(app, ["writeback", "approve", item.id])

    assert approve_result.exit_code != 0
    error_payload = json.loads(approve_result.stdout)
    assert error_payload["trace"]["steps"][0]["detail"]["code"] == "WRITEBACK_EVIDENCE_REQUIRED"
    assert len(_queue_files(tmp_ks_root)) == 1
    assert _queue_files(tmp_ks_root)[0].stem == item.id
    assert _archive_files(tmp_ks_root) == []

    reject_result = cli_runner.invoke(app, ["writeback", "reject", item.id])
    assert reject_result.exit_code == 0
    archived = _json(_archive_files(tmp_ks_root)[0])
    assert archived["id"] == item.id
    assert archived["status"] == "rejected"
    assert _queue_files(tmp_ks_root) == []


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
@pytest.mark.us3
def test_writeback_yes_reports_already_promoted_queue_item(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    first = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])
    assert first.exit_code == 0
    first_payload = json.loads(first.stdout)
    first_step = _writeback_step(first_payload)
    item_id = first_step["detail"]["id"]
    approve = cli_runner.invoke(app, ["writeback", "approve", item_id])
    assert approve.exit_code == 0
    after_archive_log = _log_text(tmp_ks_root)
    archived_path = tmp_ks_root / "writeback" / "archive" / f"{item_id}.json"
    archived_item = WritebackQueueItem.from_dict(_json(archived_path))

    result = enqueue(archived_item, paths=runtime_paths(tmp_ks_root))

    assert result.status == "already-promoted"
    assert result.id == item_id
    assert result.path == archived_path
    assert _queue_files(tmp_ks_root) == []
    assert _log_text(tmp_ks_root) == after_archive_log


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
