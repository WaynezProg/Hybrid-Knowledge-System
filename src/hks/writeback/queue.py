"""File-backed writeback review queue storage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, cast

from hks.core.manifest import atomic_write, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.core.schema import Route
from hks.errors import ExitCode, KSError
from hks.wiki_synthesis.store import blocking_file_lock

QueueStatus = Literal["pending", "approved", "rejected"]
EnqueueStatus = Literal["created", "deduped", "already-promoted"]

_QUEUE_STATUSES = {"pending", "approved", "rejected"}
_ARCHIVE_STATUSES = {"approved", "rejected"}


@dataclass(frozen=True, slots=True)
class WritebackQueueItem:
    id: str
    question: str
    answer: str
    route: Route
    source: list[Route]
    evidence: list[dict[str, object]]
    retrieval_score: float | None
    writeback_eligible: bool
    reasons: list[str] = field(default_factory=list)
    created_at: str = ""
    status: QueueStatus = "pending"
    decided_at: str | None = None
    slug: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "route": self.route,
            "source": list(self.source),
            "evidence": _normalize_evidence(self.evidence),
            "retrieval_score": self.retrieval_score,
            "writeback_eligible": self.writeback_eligible,
            "reasons": list(self.reasons),
            "created_at": self.created_at,
            "status": self.status,
            "decided_at": self.decided_at,
            "slug": self.slug,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> WritebackQueueItem:
        status = _validate_status(str(payload.get("status", "pending")))
        return cls(
            id=str(payload["id"]),
            question=str(payload["question"]),
            answer=str(payload["answer"]),
            route=cast(Route, payload["route"]),
            source=[cast(Route, route) for route in cast(list[object], payload.get("source", []))],
            evidence=_normalize_evidence(
                cast(list[dict[str, object]], payload.get("evidence", []))
            ),
            retrieval_score=_optional_float(payload.get("retrieval_score")),
            writeback_eligible=bool(payload["writeback_eligible"]),
            reasons=[str(reason) for reason in cast(list[object], payload.get("reasons", []))],
            created_at=str(payload.get("created_at", "")),
            status=status,
            decided_at=_optional_str(payload.get("decided_at")),
            slug=_optional_str(payload.get("slug")),
        )


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    status: EnqueueStatus
    id: str
    path: Path | None


@dataclass(frozen=True, slots=True)
class LockedPendingItem:
    item: WritebackQueueItem
    paths: RuntimePaths


def build_item(
    *,
    question: str,
    answer: str,
    route: Route,
    source: list[Route],
    evidence: list[dict[str, object]],
    retrieval_score: float | None,
    writeback_eligible: bool,
    reasons: list[str] | None = None,
    created_at: str | None = None,
) -> WritebackQueueItem:
    normalized_evidence = _normalize_evidence(evidence)
    item_id = _build_id(
        question=question,
        answer=answer,
        route=route,
        evidence=normalized_evidence,
    )
    return WritebackQueueItem(
        id=item_id,
        question=question,
        answer=answer,
        route=route,
        source=list(source),
        evidence=normalized_evidence,
        retrieval_score=retrieval_score,
        writeback_eligible=writeback_eligible,
        reasons=list(reasons or []),
        created_at=created_at or utc_now_iso(),
    )


def enqueue(
    item: WritebackQueueItem,
    *,
    paths: RuntimePaths | None = None,
) -> EnqueueResult:
    resolved = paths or runtime_paths()
    queue_path = _queue_path(item.id, resolved)
    archive_path = _archive_path(item.id, resolved)
    with blocking_file_lock(_lock_path(item.id, resolved)):
        if queue_path.exists():
            return EnqueueResult(status="deduped", id=item.id, path=queue_path)
        if archive_path.exists():
            archived = _read_item(archive_path)
            if archived.status == "approved":
                return EnqueueResult(status="already-promoted", id=item.id, path=archive_path)
        pending = replace(item, status="pending", decided_at=None, slug=None)
        _write_item(queue_path, pending)
        return EnqueueResult(status="created", id=item.id, path=queue_path)


def list_pending(*, paths: RuntimePaths | None = None) -> list[WritebackQueueItem]:
    resolved = paths or runtime_paths()
    queue_dir = _queue_dir(resolved)
    if not queue_dir.exists():
        return []
    items = [_read_item(path) for path in queue_dir.glob("*.json")]
    pending = [item for item in items if item.status == "pending"]
    return sorted(pending, key=lambda item: (item.created_at, item.id))


def load(item_id: str, *, paths: RuntimePaths | None = None) -> WritebackQueueItem:
    resolved = paths or runtime_paths()
    return _load_pending_unlocked(item_id, resolved)


@contextmanager
def locked_pending_item(
    item_id: str,
    *,
    paths: RuntimePaths | None = None,
) -> Iterator[LockedPendingItem]:
    resolved = paths or runtime_paths()
    with blocking_file_lock(_lock_path(item_id, resolved)):
        yield LockedPendingItem(item=_load_pending_unlocked(item_id, resolved), paths=resolved)


def archive(
    item_id: str,
    status: Literal["approved", "rejected"],
    *,
    slug: str | None = None,
    paths: RuntimePaths | None = None,
) -> WritebackQueueItem:
    if status not in _ARCHIVE_STATUSES:
        raise KSError(
            f"writeback queue archive status `{status}` 無效",
            exit_code=ExitCode.DATAERR,
            code="WRITEBACK_QUEUE_INVALID",
        )
    resolved = paths or runtime_paths()
    with blocking_file_lock(_lock_path(item_id, resolved)):
        locked = LockedPendingItem(item=_load_pending_unlocked(item_id, resolved), paths=resolved)
        return archive_locked(locked=locked, status=status, slug=slug)


def archive_locked(
    *,
    locked: LockedPendingItem,
    status: Literal["approved", "rejected"],
    slug: str | None = None,
) -> WritebackQueueItem:
    if status not in _ARCHIVE_STATUSES:
        raise KSError(
            f"writeback queue archive status `{status}` 無效",
            exit_code=ExitCode.DATAERR,
            code="WRITEBACK_QUEUE_INVALID",
        )
    queue_path = _queue_path(locked.item.id, locked.paths)
    archive_path = _archive_path(locked.item.id, locked.paths)
    if not queue_path.exists():
        raise _missing_queue_item(locked.item.id)
    item = _read_item(queue_path)
    if item.status != "pending":
        raise _missing_queue_item(locked.item.id)
    archived = replace(item, status=status, decided_at=utc_now_iso(), slug=slug)
    _write_item(archive_path, archived)
    queue_path.unlink()
    return archived


def _build_id(
    *,
    question: str,
    answer: str,
    route: Route,
    evidence: list[dict[str, object]],
) -> str:
    payload = {
        "question": question,
        "answer": answer,
        "route": route,
        "evidence": evidence,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _normalize_evidence(evidence: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {key: _normalize_json_value(value) for key, value in sorted(item.items())}
        for item in evidence
    ]


def _normalize_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _normalize_json_value(value[key])
            for key in sorted(value, key=lambda key: str(key))
        }
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def _queue_dir(paths: RuntimePaths) -> Path:
    return paths.root / "writeback" / "queue"


def _archive_dir(paths: RuntimePaths) -> Path:
    return paths.root / "writeback" / "archive"


def _queue_path(item_id: str, paths: RuntimePaths) -> Path:
    return _queue_dir(paths) / f"{item_id}.json"


def _archive_path(item_id: str, paths: RuntimePaths) -> Path:
    return _archive_dir(paths) / f"{item_id}.json"


def _lock_path(item_id: str, paths: RuntimePaths) -> Path:
    return paths.root / "writeback" / ".locks" / f"{item_id}.lock"


def _read_item(path: Path) -> WritebackQueueItem:
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise TypeError("writeback queue item must be a JSON object")
        payload = cast(dict[str, object], raw_payload)
        return WritebackQueueItem.from_dict(payload)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise KSError(
            f"writeback queue item `{path.name}` 無效",
            exit_code=ExitCode.DATAERR,
            code="WRITEBACK_QUEUE_INVALID",
            details=[str(exc)],
        ) from exc


def _load_pending_unlocked(item_id: str, paths: RuntimePaths) -> WritebackQueueItem:
    path = _queue_path(item_id, paths)
    if not path.exists():
        raise _missing_queue_item(item_id)
    item = _read_item(path)
    if item.status != "pending":
        raise _missing_queue_item(item_id)
    return item


def _write_item(path: Path, item: WritebackQueueItem) -> None:
    atomic_write(path, json.dumps(item.to_dict(), ensure_ascii=False, indent=2))


def _validate_status(status: str) -> QueueStatus:
    if status not in _QUEUE_STATUSES:
        raise ValueError(f"invalid writeback queue status: {status}")
    return cast(QueueStatus, status)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raise TypeError("retrieval_score must be a number or null")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _missing_queue_item(item_id: str) -> KSError:
    return KSError(
        f"pending writeback queue item `{item_id}` 不存在",
        exit_code=ExitCode.NOINPUT,
        code="NOINPUT",
    )
