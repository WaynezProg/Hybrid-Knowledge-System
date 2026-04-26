"""Command wrappers for 011 watch workflow."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from hks.adapters.contracts import validate_watch_summary
from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.watch.models import WatchMode, WatchProfile, WatchRequest
from hks.watch.service import run as service_run
from hks.watch.service import scan as service_scan
from hks.watch.service import status as service_status
from hks.watch.service import summary_answer


def run_scan(*, source_roots: list[Path] | None = None) -> QueryResponse:
    request = WatchRequest(operation="scan", source_roots=list(source_roots or []))
    detail, _ = service_scan(request)
    payload = detail.to_dict()
    validate_watch_summary(payload)
    return QueryResponse(
        answer=summary_answer(payload),
        source=[],
        confidence=detail.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="watch_summary", detail=payload)]),
    )


def run_watch(
    *,
    source_roots: list[Path] | None = None,
    mode: str = "dry-run",
    profile: str = "scan-only",
    prune: bool = False,
    include_llm: bool = False,
    include_wiki_apply: bool = False,
    include_graphify: bool = False,
    force: bool = False,
    requested_by: str | None = None,
) -> QueryResponse:
    request = WatchRequest(
        operation="run",
        mode=cast(WatchMode, mode),
        profile=cast(WatchProfile, profile),
        source_roots=list(source_roots or []),
        prune=prune,
        include_llm=include_llm,
        include_wiki_apply=include_wiki_apply,
        include_graphify=include_graphify,
        force=force,
        requested_by=requested_by,
    )
    detail, _ = service_run(request)
    payload = detail.to_dict()
    validate_watch_summary(payload)
    source: list[Route] = (
        ["wiki", "graph", "vector"] if mode == "execute" and profile != "scan-only" else []
    )
    return QueryResponse(
        answer=summary_answer(payload),
        source=source,
        confidence=detail.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="watch_summary", detail=payload)]),
    )


def run_status() -> QueryResponse:
    request = WatchRequest(operation="status")
    detail = service_status(request)
    payload = detail.to_dict()
    validate_watch_summary(payload)
    return QueryResponse(
        answer=summary_answer(payload),
        source=[],
        confidence=detail.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="watch_summary", detail=payload)]),
    )
