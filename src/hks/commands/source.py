"""CLI command wrappers for source catalog."""

from __future__ import annotations

from pathlib import Path

from hks.adapters.contracts import validate_catalog_summary
from hks.catalog.service import list_sources, show_source, summary_answer
from hks.core.schema import QueryResponse, Trace, TraceStep


def _response(detail: dict[str, object]) -> QueryResponse:
    validate_catalog_summary(detail)
    return QueryResponse(
        answer=summary_answer(detail),
        source=[],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="catalog_summary", detail=detail)]),
    )


def run_list(
    *,
    ks_root: Path | str | None = None,
    format: str | None = None,
    relpath_query: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> QueryResponse:
    return _response(
        list_sources(
            ks_root=ks_root,
            format=format,
            relpath_query=relpath_query,
            limit=limit,
            offset=offset,
        ).to_dict()
    )


def run_show(relpath: str, *, ks_root: Path | str | None = None) -> QueryResponse:
    return _response(show_source(relpath, ks_root=ks_root).to_dict())

