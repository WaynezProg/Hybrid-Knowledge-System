"""High-level daily update command."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.watch.models import WatchMode, WatchProfile, WatchRequest, WatchSummaryDetail
from hks.watch.service import run as service_run


def run(
    source_root: Path,
    *,
    mode: str = "execute",
    profile: str = "ingest-only",
    prune: bool = False,
) -> QueryResponse:
    source_roots = [source_root.expanduser().resolve(strict=False)]
    request = WatchRequest(
        operation="run",
        mode=cast(WatchMode, mode),
        profile=cast(WatchProfile, profile),
        source_roots=source_roots,
        prune=prune,
    )
    detail, _ = service_run(request)
    payload = _build_detail(detail, source_roots=source_roots)
    source: list[Route] = ["wiki", "graph", "vector"] if mode == "execute" else []
    return QueryResponse(
        answer=_summary_answer(payload),
        source=source,
        confidence=detail.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="update_summary", detail=payload)]),
    )


def _build_detail(
    summary: WatchSummaryDetail,
    *,
    source_roots: list[Path],
) -> dict[str, Any]:
    return {
        "kind": "update_summary",
        "operation": "update",
        "mode": summary.mode,
        "profile": summary.profile,
        "source_roots": [root.as_posix() for root in source_roots],
        "plan_id": summary.plan_id,
        "run_id": summary.run_id,
        "plan_fingerprint": summary.plan_fingerprint,
        "source_counts": summary.source_counts,
        "action_counts": summary.action_counts,
        "artifacts": summary.artifacts,
    }


def _summary_answer(detail: dict[str, object]) -> str:
    counts = cast(dict[str, int], detail["source_counts"])
    action = cast(dict[str, int], detail["action_counts"])
    return (
        "update 完成："
        f"{counts.get('stale', 0)} updated / {counts.get('new', 0)} new / "
        f"{counts.get('missing', 0)} missing；"
        f"{action.get('completed', 0)} completed / {action.get('failed', 0)} failed"
    )
