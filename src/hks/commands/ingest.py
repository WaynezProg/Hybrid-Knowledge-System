"""CLI entry for ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hks.core.ingest_contract import validate_ingest_detail
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.ingest.models import IngestFileReport, IngestSummary
from hks.ingest.office_common import SkippedSegment
from hks.ingest.pipeline import ingest as run_ingest


def _serialize_skipped(segments: list[SkippedSegment]) -> list[dict[str, Any]]:
    aggregated: dict[str, int] = {}
    for segment in segments:
        aggregated[segment.type] = aggregated.get(segment.type, 0) + segment.count
    return [{"type": kind, "count": count} for kind, count in sorted(aggregated.items())]


def _serialize_file(report: IngestFileReport) -> dict[str, Any]:
    return {
        "path": report.path,
        "status": report.status,
        "reason": report.reason,
        "skipped_segments": _serialize_skipped(report.skipped_segments),
        "pptx_notes": report.pptx_notes,
    }


def _summary_to_response(summary: IngestSummary) -> QueryResponse:
    detail: dict[str, Any] = {
        "created": summary.created,
        "updated": summary.updated,
        "skipped": [{"path": issue.path, "reason": issue.reason} for issue in summary.skipped],
        "failures": [{"path": issue.path, "reason": issue.reason} for issue in summary.failures],
        "pruned": summary.pruned,
        "files": [_serialize_file(report) for report in summary.files],
    }
    validate_ingest_detail(detail)
    return QueryResponse(
        answer=summary.answer(),
        source=[],
        confidence=0.0,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="ingest_summary", detail=detail)],
        ),
    )


def run(path: Path, *, prune: bool = False, pptx_notes: bool = True) -> QueryResponse:
    summary = run_ingest(path, prune=prune, pptx_notes=pptx_notes)
    response = _summary_to_response(summary)
    if summary.failures:
        raise KSError(
            "ingest 完成，但有資料錯誤",
            exit_code=ExitCode.DATAERR,
            code="DATAERR",
            details=[f"{issue.path}: {issue.reason}" for issue in summary.failures],
            response=response,
        )
    return response
