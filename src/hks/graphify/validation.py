"""Schema validation for 010 Graphify."""

from __future__ import annotations

from hks.adapters.contracts import (
    validate_graphify_graph,
    validate_graphify_run,
    validate_graphify_summary,
)
from hks.errors import ExitCode, KSError
from hks.graphify.models import GraphifyGraph, GraphifyResult, GraphifyRun


def validate_graph(graph: GraphifyGraph) -> GraphifyGraph:
    try:
        validate_graphify_graph(graph.to_dict())
    except Exception as exc:
        raise KSError(
            "graphify graph artifact 無效",
            exit_code=ExitCode.DATAERR,
            code="GRAPHIFY_GRAPH_INVALID",
            details=[str(exc)],
            route="graph",
        ) from exc
    return graph


def validate_run(run: GraphifyRun) -> GraphifyRun:
    try:
        validate_graphify_run(run.to_dict())
    except Exception as exc:
        raise KSError(
            "graphify run artifact 無效",
            exit_code=ExitCode.DATAERR,
            code="GRAPHIFY_RUN_INVALID",
            details=[str(exc)],
            route="graph",
        ) from exc
    return run


def validate_result(result: GraphifyResult) -> GraphifyResult:
    try:
        validate_graphify_summary(result.to_detail())
    except Exception as exc:
        raise KSError(
            "graphify summary 無效",
            exit_code=ExitCode.DATAERR,
            code="GRAPHIFY_SUMMARY_INVALID",
            details=[str(exc)],
            route="graph",
        ) from exc
    return result
