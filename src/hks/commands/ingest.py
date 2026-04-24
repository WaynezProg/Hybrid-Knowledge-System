"""CLI entry for ingestion."""

from __future__ import annotations

from pathlib import Path

from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.ingest.models import IngestSummary
from hks.ingest.pipeline import ingest as run_ingest


def _summary_to_response(summary: IngestSummary) -> QueryResponse:
    return QueryResponse(
        answer=summary.answer(),
        source=[],
        confidence=0.0,
        trace=Trace(
            route="wiki",
            steps=[
                TraceStep(
                    kind="ingest_summary",
                    detail={
                        "created": summary.created,
                        "updated": summary.updated,
                        "skipped": [
                            {"path": issue.path, "reason": issue.reason}
                            for issue in summary.skipped
                        ],
                        "failures": [
                            {"path": issue.path, "reason": issue.reason}
                            for issue in summary.failures
                        ],
                        "pruned": summary.pruned,
                    },
                )
            ],
        ),
    )


def run(path: Path, *, prune: bool = False) -> QueryResponse:
    summary = run_ingest(path, prune=prune)
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
