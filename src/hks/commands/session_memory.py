"""CLI command wrappers for structured session-memory summaries."""

from __future__ import annotations

from datetime import date

from hks.core.manifest import resume_or_rebuild
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.retrieval.evidence import candidate_evidence
from hks.retrievers.session_memory import (
    collect_session_memory_candidates,
    synthesize_date_range_summary,
)
from hks.routing.session_memory import SessionMemoryIntent
from hks.storage.wiki import WikiStore


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise KSError(
            f"{field_name} 必須為 YYYY-MM-DD 格式",
            exit_code=ExitCode.USAGE,
            code="USAGE",
            hint=f"example: {field_name} 2026-05-25",
        ) from exc


def run_summary(
    *,
    date_from: str,
    date_to: str,
    workspace: str | None = None,
) -> QueryResponse:
    paths = runtime_paths()
    if not paths.manifest.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )

    manifest = resume_or_rebuild(paths)
    if not manifest.entries:
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )

    start = _parse_iso_date(date_from, "--from")
    end = _parse_iso_date(date_to, "--to")
    if start > end:
        start, end = end, start

    intent = SessionMemoryIntent(
        date_start=start,
        date_end=end,
        workspace=workspace,
    )
    wiki_store = WikiStore(paths)
    candidates, lookup_steps = collect_session_memory_candidates(
        "",
        wiki_store=wiki_store,
        intent=intent,
    )
    summary = synthesize_date_range_summary(
        candidates,
        intent,
        allow_single_day=True,
    )

    steps = list(lookup_steps)
    if summary is None:
        steps.append(
            TraceStep(
                kind="session_memory_summary",
                detail={
                    "hit": False,
                    "date_start": start,
                    "date_end": end,
                    "workspace": workspace,
                },
            )
        )
        return QueryResponse(
            answer="指定日期範圍內找不到 session daily 資料",
            source=[],
            confidence=0.0,
            trace=Trace(route="wiki", steps=steps),
            writeback_eligible=False,
        )

    steps.append(
        TraceStep(
            kind="session_memory_summary",
            detail={
                "hit": True,
                "date_start": start,
                "date_end": end,
                "workspace": workspace,
                "entry_count": summary.metadata.get("entry_count"),
                "source_relpaths": summary.metadata.get("source_relpaths"),
            },
        )
    )
    evidence = candidate_evidence(summary)
    return QueryResponse(
        answer=summary.text,
        source=[summary.source_route],
        confidence=1.0,
        trace=Trace(route=summary.source_route, steps=steps),
        evidence=evidence,
        retrieval_score=summary.score,
        calibrated_confidence=summary.score,
        writeback_eligible=False,
    )
