from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.core.paths import runtime_paths
from hks.writeback.queue import build_item, enqueue


def _payload(result: Any) -> dict[str, Any]:
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _seed_item(
    *,
    question: str = "Project Atlas summary",
    created_at: str = "2026-05-22T01:00:00+00:00",
) -> str:
    item = build_item(
        question=question,
        answer="Atlas is active.",
        route="vector",
        source=["vector"],
        evidence=[
            {
                "route": "vector",
                "source_relpath": "atlas.txt",
                "quote": "Atlas source quote",
            }
        ],
        retrieval_score=0.82,
        writeback_eligible=True,
        reasons=["vector evidence with source"],
        created_at=created_at,
    )
    enqueue(item, paths=runtime_paths())
    return item.id


@pytest.mark.unit
def test_writeback_list_empty_queue_returns_items_empty(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["writeback", "list"])

    assert result.exit_code == 0, result.output
    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["answer"] == "writeback list 完成：0 items"
    assert detail == {"status": "listed", "items": []}


@pytest.mark.unit
def test_writeback_list_sorts_pending_items_and_exposes_review_fields(
    cli_runner: CliRunner,
) -> None:
    later_id = _seed_item(question="Later question", created_at="2026-05-22T02:00:00+00:00")
    earlier_id = _seed_item(question="Earlier question", created_at="2026-05-22T01:00:00+00:00")

    result = cli_runner.invoke(app, ["writeback", "list"])

    assert result.exit_code == 0, result.output
    items = _payload(result)["trace"]["steps"][0]["detail"]["items"]
    assert [item["id"] for item in items] == [earlier_id, later_id]
    assert items[0] == {
        "id": earlier_id,
        "route": "vector",
        "retrieval_score": 0.82,
        "writeback_eligible": True,
        "question": "Earlier question",
        "question_preview": "Earlier question",
        "created_at": "2026-05-22T01:00:00+00:00",
    }


@pytest.mark.unit
def test_writeback_show_outputs_full_pending_item(cli_runner: CliRunner) -> None:
    item_id = _seed_item()

    result = cli_runner.invoke(app, ["writeback", "show", item_id])

    assert result.exit_code == 0, result.output
    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["answer"] == f"writeback show 完成：{item_id}"
    assert payload["evidence"] == [
        {"quote": "Atlas source quote", "route": "vector", "source_relpath": "atlas.txt"}
    ]
    assert detail["status"] == "shown"
    assert detail["item"]["id"] == item_id
    assert detail["item"]["reasons"] == ["vector evidence with source"]


@pytest.mark.unit
def test_writeback_approve_promotes_then_archives(cli_runner: CliRunner) -> None:
    item_id = _seed_item()

    result = cli_runner.invoke(app, ["writeback", "approve", item_id])

    assert result.exit_code == 0, result.output
    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["answer"] == "writeback approve 完成：project-atlas-summary"
    assert payload["source"] == ["wiki"]
    assert detail["status"] == "approved"
    assert detail["slug"] == "project-atlas-summary"
    assert detail["archive"]["status"] == "approved"
    assert detail["archive"]["id"] == item_id
    assert not (runtime_paths().root / "writeback" / "queue" / f"{item_id}.json").exists()
    assert (runtime_paths().root / "writeback" / "archive" / f"{item_id}.json").exists()


@pytest.mark.unit
def test_writeback_reject_archives_without_wiki_write(cli_runner: CliRunner) -> None:
    item_id = _seed_item()

    result = cli_runner.invoke(app, ["writeback", "reject", item_id])

    assert result.exit_code == 0, result.output
    payload = _payload(result)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["answer"] == f"writeback reject 完成：{item_id}"
    assert payload["source"] == []
    assert detail["status"] == "rejected"
    assert detail["archive"]["id"] == item_id
    assert not list(runtime_paths().wiki_pages.glob("*.md"))


@pytest.mark.unit
@pytest.mark.parametrize("subcommand", ["show", "approve", "reject"])
def test_writeback_missing_id_returns_noinput_error_payload(
    cli_runner: CliRunner,
    subcommand: str,
) -> None:
    result = cli_runner.invoke(app, ["writeback", subcommand, "missing"])

    assert result.exit_code == 66
    assert result.stderr.splitlines()[0].startswith(f"[ks:writeback {subcommand}] error:")
    payload = _payload(result)
    assert payload["trace"]["steps"][0]["detail"] == {"code": "NOINPUT", "exit_code": 66}


@pytest.mark.unit
def test_writeback_approve_invalid_evidence_keeps_item_pending(cli_runner: CliRunner) -> None:
    item = build_item(
        question="Invalid evidence",
        answer="Synthetic answer",
        route="wiki",
        source=["wiki"],
        evidence=[{"route": "wiki", "source_relpath": "<writeback>", "quote": "synthetic"}],
        retrieval_score=0.8,
        writeback_eligible=True,
    )
    enqueue(item, paths=runtime_paths())

    result = cli_runner.invoke(app, ["writeback", "approve", item.id])

    assert result.exit_code == 65
    assert (runtime_paths().root / "writeback" / "queue" / f"{item.id}.json").exists()
    assert not (runtime_paths().root / "writeback" / "archive" / f"{item.id}.json").exists()
