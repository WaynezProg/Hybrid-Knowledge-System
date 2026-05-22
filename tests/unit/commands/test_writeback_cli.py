from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.commands import writeback as writeback_command
from hks.core.lock import blocking_file_lock
from hks.core.manifest import Manifest, ManifestEntry, compute_sha256, save_manifest, utc_now_iso
from hks.core.paths import runtime_paths
from hks.core.schema import TraceStep
from hks.errors import ExitCode, KSError
from hks.storage.wiki import WikiStore
from hks.writeback.queue import build_item, enqueue


def _payload(result: Any) -> dict[str, Any]:
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _seed_item(
    *,
    question: str = "Project Atlas summary",
    created_at: str = "2026-05-22T01:00:00+00:00",
    retrieval_score: float | None = 0.82,
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
        retrieval_score=retrieval_score,
        writeback_eligible=True,
        reasons=["vector evidence with source"],
        created_at=created_at,
    )
    enqueue(item, paths=runtime_paths())
    return item.id


def _seed_source(relpath: str = "atlas.txt") -> None:
    paths = runtime_paths()
    raw_path = paths.raw_sources / relpath
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("Atlas source quote", encoding="utf-8")
    save_manifest(
        Manifest(
            entries={
                relpath: ManifestEntry(
                    relpath=relpath,
                    sha256=compute_sha256(raw_path),
                    format="txt",
                    size_bytes=raw_path.stat().st_size,
                    ingested_at=utc_now_iso(),
                )
            }
        ),
        paths.manifest,
    )


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
def test_writeback_show_unknown_retrieval_score_uses_zero_confidence(
    cli_runner: CliRunner,
) -> None:
    item_id = _seed_item(retrieval_score=None)

    result = cli_runner.invoke(app, ["writeback", "show", item_id])

    assert result.exit_code == 0, result.output
    payload = _payload(result)
    assert payload["confidence"] == 0.0
    assert "retrieval_score" not in payload


@pytest.mark.unit
@pytest.mark.parametrize(
    ("retrieval_score", "expected_confidence"),
    [(1.2, 1.0), (-0.2, 0.0)],
)
def test_writeback_show_clamps_confidence_to_response_schema_range(
    cli_runner: CliRunner,
    retrieval_score: float,
    expected_confidence: float,
) -> None:
    item_id = _seed_item(retrieval_score=retrieval_score)

    result = cli_runner.invoke(app, ["writeback", "show", item_id])

    assert result.exit_code == 0, result.output
    payload = _payload(result)
    assert payload["confidence"] == expected_confidence
    assert payload["retrieval_score"] == retrieval_score


@pytest.mark.unit
def test_writeback_approve_promotes_then_archives(cli_runner: CliRunner) -> None:
    _seed_source()
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
def test_writeback_approve_waits_for_wikistore_mutation_lock() -> None:
    _seed_source()
    item_id = _seed_item()
    paths = runtime_paths()
    project_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{project_root / 'src'}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(project_root / "src")
    )
    code = """
import sys
from hks.commands.writeback import run_approve

print(run_approve(sys.argv[1]).to_json())
"""

    with blocking_file_lock(WikiStore(paths).mutation_lock_path):
        process = subprocess.Popen(
            [sys.executable, "-c", code, item_id],
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.3)
        assert process.poll() is None
        assert not (paths.wiki_pages / "project-atlas-summary.md").exists()

    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, stderr
    payload = json.loads(stdout)
    assert payload["answer"] == "writeback approve 完成：project-atlas-summary"
    assert payload["trace"]["steps"][0]["detail"]["slug"] == "project-atlas-summary"


@pytest.mark.unit
def test_writeback_approve_missing_pending_item_does_not_promote(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = _seed_item()
    cli_runner.invoke(app, ["writeback", "reject", item_id])
    calls: list[str] = []

    def fake_promote(**_: object) -> list[TraceStep]:
        calls.append("promote")
        return []

    monkeypatch.setattr(writeback_command, "promote", fake_promote)

    result = cli_runner.invoke(app, ["writeback", "approve", item_id])

    assert result.exit_code == 66
    assert calls == []


@pytest.mark.unit
def test_writeback_approve_archive_failure_after_promote_reports_partial_success(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_source()
    item_id = _seed_item()

    def fail_archive_locked(**_: object) -> object:
        raise KSError("archive failed", exit_code=ExitCode.GENERAL, code="ARCHIVE_FAILED")

    monkeypatch.setattr(writeback_command, "archive_locked", fail_archive_locked)

    result = cli_runner.invoke(app, ["writeback", "approve", item_id])

    assert result.exit_code == 1
    assert (runtime_paths().wiki_pages / "project-atlas-summary.md").exists()
    assert (runtime_paths().root / "writeback" / "queue" / f"{item_id}.json").exists()
    payload = _payload(result)
    assert payload["source"] == []
    detail = payload["trace"]["steps"][0]["detail"]
    assert detail == {"code": "WRITEBACK_APPROVE_PARTIAL", "exit_code": 1}
    assert "partial writeback approval" in payload["answer"]
    assert "item_id" not in result.stdout
    assert "project-atlas-summary" not in result.stdout
    assert item_id in result.stderr
    assert "item_id=" in result.stderr
    assert "slug=project-atlas-summary" in result.stderr
    assert "project-atlas-summary" in result.stderr


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
