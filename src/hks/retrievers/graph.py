"""Graph candidate retrieval."""

from __future__ import annotations

from collections.abc import Sequence

from hks.core.schema import TraceStep
from hks.graph.query import answer_query
from hks.graph.store import GraphStore
from hks.retrieval.models import Candidate


def graph_trace_detail(
    *,
    relpaths: list[str],
    node_ids: list[str],
    edge_ids: list[str],
    relations: Sequence[str],
    evidence_by_relpath: dict[str, str] | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "hit": True,
        "relpaths": relpaths,
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "relations": relations,
    }
    if evidence_by_relpath:
        detail["evidence_by_relpath"] = evidence_by_relpath
    return detail



def collect_graph_candidates(
    question: str,
    *,
    graph_store: GraphStore,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    graph_result = answer_query(question, graph_store)
    if graph_result is None:
        steps.append(TraceStep(kind="graph_lookup", detail={"hit": False}))
        return candidates, steps

    graph_payload = graph_store.load()
    evidence_by_relpath: dict[str, str] = {}
    for edge_id in graph_result.edge_ids:
        edge = graph_payload.edges.get(edge_id)
        if edge is not None and edge.evidence:
            evidence_by_relpath.setdefault(edge.source_relpath, edge.evidence)

    steps.append(
        TraceStep(
            kind="graph_lookup",
            detail=graph_trace_detail(
                relpaths=graph_result.relpaths,
                node_ids=graph_result.node_ids,
                edge_ids=graph_result.edge_ids,
                relations=graph_result.relations,
                evidence_by_relpath=evidence_by_relpath,
            ),
        )
    )
    candidates.append(
        Candidate(
            text=graph_result.answer,
            source_route="graph",
            score=graph_result.confidence,
            metadata={
                "relpaths": graph_result.relpaths,
                "edge_ids": graph_result.edge_ids,
                "evidence_by_relpath": evidence_by_relpath,
            },
        )
    )
    return candidates, steps
