"""Command wrappers for the writeback review queue."""

from __future__ import annotations

from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.writeback.queue import (
    WritebackQueueItem,
    archive,
    archive_locked,
    load,
    locked_pending_item,
)
from hks.writeback.queue import (
    list_pending as queue_list_pending,
)
from hks.writeback.writer import promote

_QUESTION_PREVIEW_CHARS = 120


def run_list() -> QueryResponse:
    items = [_summary(item) for item in queue_list_pending()]
    return QueryResponse(
        answer=f"writeback list 完成：{len(items)} items",
        source=[],
        confidence=1.0,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="writeback", detail={"status": "listed", "items": items})],
        ),
    )


def run_show(item_id: str) -> QueryResponse:
    item = load(item_id)
    detail = {"status": "shown", "item": item.to_dict()}
    return QueryResponse(
        answer=f"writeback show 完成：{item.id}",
        source=[],
        confidence=_confidence(item),
        evidence=item.evidence,
        retrieval_score=item.retrieval_score,
        writeback_eligible=item.writeback_eligible,
        trace=Trace(route=item.route, steps=[TraceStep(kind="writeback", detail=detail)]),
    )


def run_approve(item_id: str) -> QueryResponse:
    with locked_pending_item(item_id) as locked:
        item = locked.item
        steps = promote(item=item)
        approved_step = _first_writeback_step(steps)
        slug = str(approved_step.detail["slug"])
        try:
            archived = archive_locked(locked=locked, status="approved", slug=slug)
        except Exception as exc:
            raise KSError(
                "partial writeback approval: wiki 已寫入但 queue archive 失敗",
                exit_code=ExitCode.GENERAL,
                code="WRITEBACK_APPROVE_PARTIAL",
                details=[f"item_id={item.id}", f"slug={slug}", str(exc)],
            ) from exc
    detail = {
        **approved_step.detail,
        "archive": archived.to_dict(),
    }
    return QueryResponse(
        answer=f"writeback approve 完成：{slug}",
        source=["wiki"],
        confidence=_confidence(item),
        evidence=item.evidence,
        retrieval_score=item.retrieval_score,
        writeback_eligible=item.writeback_eligible,
        trace=Trace(route=item.route, steps=[TraceStep(kind="writeback", detail=detail)]),
    )


def run_reject(item_id: str) -> QueryResponse:
    archived = archive(item_id, "rejected")
    detail = {
        "status": "rejected",
        "archive": archived.to_dict(),
    }
    return QueryResponse(
        answer=f"writeback reject 完成：{item_id}",
        source=[],
        confidence=1.0,
        trace=Trace(route=archived.route, steps=[TraceStep(kind="writeback", detail=detail)]),
    )


def _summary(item: WritebackQueueItem) -> dict[str, object]:
    return {
        "id": item.id,
        "route": item.route,
        "retrieval_score": item.retrieval_score,
        "writeback_eligible": item.writeback_eligible,
        "question": item.question,
        "question_preview": _preview(item.question),
        "created_at": item.created_at,
    }


def _preview(question: str) -> str:
    if len(question) <= _QUESTION_PREVIEW_CHARS:
        return question
    return f"{question[: _QUESTION_PREVIEW_CHARS - 3]}..."


def _confidence(item: WritebackQueueItem) -> float:
    return item.retrieval_score if item.retrieval_score is not None else 0.0


def _first_writeback_step(steps: list[TraceStep]) -> TraceStep:
    for step in steps:
        if step.kind == "writeback" and "slug" in step.detail:
            return step
    raise RuntimeError("promote() did not return an approved writeback step")
