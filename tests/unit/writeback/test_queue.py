from __future__ import annotations

import json

import pytest

import hks.writeback.queue as queue_module
from hks.core.paths import runtime_paths
from hks.errors import ExitCode, KSError
from hks.writeback.queue import (
    archive,
    archive_locked,
    build_item,
    enqueue,
    list_pending,
    load,
    locked_pending_item,
)


def _item(
    *,
    question: str = "What is Project Atlas?",
    answer: str = "Project Atlas is active.",
    evidence: list[dict[str, object]] | None = None,
    reasons: list[str] | None = None,
    retrieval_score: float | None = 0.82,
    writeback_eligible: bool = True,
    created_at: str = "2026-05-22T01:00:00+00:00",
):
    return build_item(
        question=question,
        answer=answer,
        route="wiki",
        source=["wiki", "vector"],
        evidence=evidence
        if evidence is not None
        else [{"source_relpath": "atlas.md", "quote": "Atlas", "route": "wiki"}],
        retrieval_score=retrieval_score,
        writeback_eligible=writeback_eligible,
        reasons=reasons or ["high confidence"],
        created_at=created_at,
    )


@pytest.mark.unit
def test_build_item_id_is_deterministic_for_same_input() -> None:
    assert _item().id == _item().id


@pytest.mark.unit
def test_build_item_id_changes_when_evidence_quote_or_source_changes() -> None:
    base = _item(evidence=[{"source_relpath": "atlas.md", "quote": "Atlas", "route": "wiki"}])

    quote_changed = _item(
        evidence=[{"source_relpath": "atlas.md", "quote": "Different", "route": "wiki"}]
    )
    source_changed = _item(
        evidence=[{"source_relpath": "other.md", "quote": "Atlas", "route": "wiki"}]
    )

    assert quote_changed.id != base.id
    assert source_changed.id != base.id


@pytest.mark.unit
def test_build_item_id_ignores_review_metadata() -> None:
    base = _item()
    changed = _item(
        reasons=["needs review"],
        retrieval_score=0.1,
        writeback_eligible=False,
        created_at="2026-05-23T01:00:00+00:00",
    )

    assert changed.id == base.id


@pytest.mark.unit
def test_enqueue_created_writes_pending_file(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()

    result = enqueue(item, paths=paths)

    assert result.status == "created"
    assert result.id == item.id
    assert result.path == paths.root / "writeback" / "queue" / f"{item.id}.json"
    assert result.path.exists()
    payload = json.loads(result.path.read_text(encoding="utf-8"))
    assert payload["status"] == "pending"


@pytest.mark.unit
def test_enqueue_same_item_returns_deduped(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()

    enqueue(item, paths=paths)
    result = enqueue(item, paths=paths)

    assert result.status == "deduped"
    assert result.path == paths.root / "writeback" / "queue" / f"{item.id}.json"


@pytest.mark.unit
def test_enqueue_approved_archive_returns_already_promoted(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()

    enqueue(item, paths=paths)
    archived = archive(item.id, "approved", slug="project-atlas", paths=paths)
    result = enqueue(_item(), paths=paths)

    assert archived.status == "approved"
    assert result.status == "already-promoted"
    assert result.path == paths.root / "writeback" / "archive" / f"{item.id}.json"


@pytest.mark.unit
def test_enqueue_approved_archive_same_question_different_content_creates_new_item(
    tmp_path,
) -> None:
    paths = runtime_paths(tmp_path / "ks")
    approved = _item(
        question="What is Project Atlas?",
        answer="Project Atlas is active.",
        evidence=[{"source_relpath": "atlas.md", "quote": "Atlas", "route": "wiki"}],
    )
    changed = _item(
        question="What is Project Atlas?",
        answer="Project Atlas is delayed.",
        evidence=[{"source_relpath": "status.md", "quote": "Delayed", "route": "wiki"}],
    )
    assert changed.id != approved.id

    enqueue(approved, paths=paths)
    archive(approved.id, "approved", slug="project-atlas", paths=paths)
    result = enqueue(changed, paths=paths)

    assert result.status == "created"
    assert result.id == changed.id
    assert result.path == paths.root / "writeback" / "queue" / f"{changed.id}.json"
    assert result.path.exists()


@pytest.mark.unit
def test_enqueue_rejected_archive_allows_requeue(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()

    enqueue(item, paths=paths)
    archive(item.id, "rejected", paths=paths)
    result = enqueue(_item(), paths=paths)

    assert result.status == "created"
    assert (paths.root / "writeback" / "queue" / f"{item.id}.json").exists()


@pytest.mark.unit
def test_list_pending_sorts_by_created_at_then_id(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    first = _item(question="b", created_at="2026-05-22T01:00:00+00:00")
    second = _item(question="a", created_at="2026-05-22T01:00:00+00:00")
    third = _item(question="c", created_at="2026-05-22T00:00:00+00:00")
    for item in [first, second, third]:
        enqueue(item, paths=paths)

    pending = list_pending(paths=paths)

    assert pending == sorted([first, second, third], key=lambda item: (item.created_at, item.id))


@pytest.mark.unit
def test_list_pending_skips_files_removed_during_iteration(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()
    enqueue(item, paths=paths)
    real_read = queue_module._read_item

    def vanishing_read(path):
        if path.stem == item.id:
            raise FileNotFoundError(path)
        return real_read(path)

    monkeypatch.setattr(queue_module, "_read_item", vanishing_read)

    assert list_pending(paths=paths) == []


@pytest.mark.unit
def test_load_missing_id_raises_noinput(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")

    with pytest.raises(KSError) as exc_info:
        load("missing", paths=paths)

    assert exc_info.value.exit_code == ExitCode.NOINPUT
    assert exc_info.value.code == "NOINPUT"
    assert "missing" in exc_info.value.message


@pytest.mark.unit
def test_load_corrupt_queue_artifact_raises_invalid_queue_error(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item_id = "corrupt"
    queue_path = paths.root / "writeback" / "queue" / f"{item_id}.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(KSError) as exc_info:
        load(item_id, paths=paths)

    assert exc_info.value.exit_code == ExitCode.DATAERR
    assert exc_info.value.code == "WRITEBACK_QUEUE_INVALID"


@pytest.mark.unit
def test_locked_pending_item_yields_current_pending_item(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()
    enqueue(item, paths=paths)

    with locked_pending_item(item.id, paths=paths) as locked:
        assert locked.item.id == item.id
        assert locked.paths == paths


@pytest.mark.unit
def test_archive_locked_archives_without_reentering_item_lock(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()
    enqueue(item, paths=paths)

    with locked_pending_item(item.id, paths=paths) as locked:
        archived = archive_locked(locked=locked, status="approved", slug="project-atlas")

    assert archived.status == "approved"
    assert not (paths.root / "writeback" / "queue" / f"{item.id}.json").exists()
    assert (paths.root / "writeback" / "archive" / f"{item.id}.json").exists()


@pytest.mark.unit
@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_archive_sets_decision_fields_and_removes_queue_file(tmp_path, status) -> None:
    paths = runtime_paths(tmp_path / "ks")
    item = _item()
    enqueue(item, paths=paths)

    archived = archive(item.id, status, slug="project-atlas", paths=paths)

    assert archived.status == status
    assert archived.decided_at
    assert archived.slug == "project-atlas"
    assert not (paths.root / "writeback" / "queue" / f"{item.id}.json").exists()
    assert (paths.root / "writeback" / "archive" / f"{item.id}.json").exists()


@pytest.mark.unit
def test_archive_missing_id_raises_noinput(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")

    with pytest.raises(KSError) as exc_info:
        archive("missing", "approved", paths=paths)

    assert exc_info.value.exit_code == ExitCode.NOINPUT
    assert exc_info.value.code == "NOINPUT"
    assert "pending writeback queue item `missing` 不存在" in exc_info.value.message
