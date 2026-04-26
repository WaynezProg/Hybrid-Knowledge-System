"""Command wrappers for 010 Graphify."""

from __future__ import annotations

from hks.adapters.contracts import validate_graphify_summary
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.graphify.config import build_request
from hks.graphify.service import build


def run_build(
    *,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    algorithm_version: str | None = None,
    include_html: bool = True,
    include_report: bool = True,
    force_new_run: bool = False,
    requested_by: str | None = None,
) -> QueryResponse:
    request = build_request(
        mode=mode,
        provider=provider,
        model=model,
        algorithm_version=algorithm_version,
        include_html=include_html,
        include_report=include_report,
        force_new_run=force_new_run,
        requested_by=requested_by,
    )
    result = build(request)
    detail = result.to_detail()
    validate_graphify_summary(detail)
    return QueryResponse(
        answer=(
            f"graphify {result.mode} 完成："
            f"{detail['node_count']} nodes, {detail['edge_count']} edges, "
            f"{detail['community_count']} communities"
        ),
        source=result.source,
        confidence=result.confidence,
        trace=Trace(route="graph", steps=[TraceStep(kind="graphify_summary", detail=detail)]),
    )
