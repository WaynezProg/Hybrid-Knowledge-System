"""CLI entry for retrieval and optional write-back."""

from __future__ import annotations

import sys
from typing import cast

from hks.core.manifest import resume_or_rebuild, utc_now_iso
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.graph.store import GraphStore
from hks.page_tree.store import TreeStore
from hks.rerank.llm import rerank_candidates
from hks.retrieval.confidence import ConfidenceAssessment, assess
from hks.retrieval.evidence import candidate_evidence
from hks.retrieval.models import Candidate
from hks.retrievers.graph import collect_graph_candidates
from hks.retrievers.page_tree import collect_page_tree_candidates
from hks.retrievers.vector import collect_vector_candidates
from hks.retrievers.wiki import collect_wiki_candidates
from hks.routing.router import route as route_query
from hks.routing.rules import load_rules
from hks.storage.vector import VectorStore
from hks.storage.wiki import LogEntry, WikiStore
from hks.writeback.gate import WritebackFlag, decide
from hks.writeback.queue import WritebackQueueItem, build_item, enqueue

_FINAL_SCORE_THRESHOLDS: dict[Route, float] = {
    "vector": 0.25,
}
_VECTOR_PRIMARY_FINAL_SCORE_THRESHOLD = 0.2
_VECTOR_LEXICAL_FINAL_SCORE_THRESHOLD = 0.4


def _build_no_hit_response(route: Route, steps: list[TraceStep]) -> QueryResponse:
    return QueryResponse(
        answer="未能於現有知識中找到答案",
        source=[],
        confidence=0.0,
        trace=Trace(route=route, steps=steps),
    )


def _final_score_threshold(
    candidate: Candidate,
    *,
    requested_route: Route | None = None,
) -> float:
    if candidate.source_route == "vector":
        if requested_route == "vector":
            return _VECTOR_PRIMARY_FINAL_SCORE_THRESHOLD
        lexical_overlap = candidate.metadata.get("lexical_overlap")
        if isinstance(lexical_overlap, int) and lexical_overlap > 0:
            return _VECTOR_LEXICAL_FINAL_SCORE_THRESHOLD
    return _FINAL_SCORE_THRESHOLDS.get(candidate.source_route, 0.0)


def _passes_final_score_gate(
    candidate: Candidate,
    *,
    requested_route: Route | None = None,
) -> bool:
    return candidate.score >= _final_score_threshold(
        candidate,
        requested_route=requested_route,
    )


def _retrieval_score_for_assessment(candidate: Candidate) -> float:
    if candidate.source_route == "vector":
        vector_similarity = candidate.metadata.get("vector_similarity")
        if isinstance(vector_similarity, int | float):
            return float(vector_similarity)
    return candidate.score


def run(question: str, *, writeback: str = "no") -> QueryResponse:
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

    rule_set = load_rules(paths.root)
    decision = route_query(question, rule_set)
    steps = list(decision.steps)
    wiki_store = WikiStore(paths)
    graph_store = GraphStore(paths)
    vector_store = VectorStore(paths)

    all_candidates: list[Candidate] = []

    wiki_candidates, wiki_steps = collect_wiki_candidates(
        question,
        wiki_store=wiki_store,
        require_secondary_intent=(decision.route != "wiki"),
        is_primary=(decision.route == "wiki"),
    )
    all_candidates.extend(wiki_candidates)
    steps.extend(wiki_steps)

    graph_candidates, graph_steps = collect_graph_candidates(
        question, graph_store=graph_store
    )
    all_candidates.extend(graph_candidates)
    steps.extend(graph_steps)

    vector_candidates, vector_steps = collect_vector_candidates(
        question, vector_store=vector_store, manifest=manifest
    )
    all_candidates.extend(vector_candidates)
    steps.extend(vector_steps)

    tree_store = TreeStore(paths)
    page_tree_candidates, page_tree_steps = collect_page_tree_candidates(
        question, tree_store=tree_store, manifest=manifest
    )
    all_candidates.extend(page_tree_candidates)
    steps.extend(page_tree_steps)

    if not all_candidates:
        response = _build_no_hit_response(decision.route, steps)
        return _maybe_enqueue(
            question=question, response=response, writeback=writeback, wiki_store=wiki_store
        )

    ranked, strategy, rerank_detail = rerank_candidates(question, all_candidates)
    steps.append(TraceStep(kind="rerank", detail=rerank_detail))
    steps.append(
        TraceStep(
            kind="merge",
            detail={
                "strategy": strategy,
                "candidate_count": len(all_candidates),
                "top_candidate": {
                    "route": ranked[0].source_route,
                    "score": ranked[0].score,
                },
            },
        )
    )

    winner = ranked[0]
    if not _passes_final_score_gate(winner, requested_route=decision.route):
        steps.append(
            TraceStep(
                kind="fallback",
                detail={
                    "status": "no-hit",
                    "reason": "final_score_below_threshold",
                    "route": winner.source_route,
                    "score": winner.score,
                    "threshold": _final_score_threshold(
                        winner,
                        requested_route=decision.route,
                    ),
                },
            )
        )
        response = _build_no_hit_response(decision.route, steps)
        return _maybe_enqueue(
            question=question,
            response=response,
            writeback=writeback,
            wiki_store=wiki_store,
        )

    evidence = candidate_evidence(winner)
    retrieval_score = _retrieval_score_for_assessment(winner)
    assessment = assess(
        route=winner.source_route,
        raw_score=retrieval_score,
        evidence=evidence,
        metadata=dict(winner.metadata),
    )

    response = QueryResponse(
        answer=winner.text,
        source=[winner.source_route],
        confidence=assessment.confidence,
        trace=Trace(route=winner.source_route, steps=steps),
        evidence=evidence,
        retrieval_score=assessment.retrieval_score,
        writeback_eligible=assessment.writeback_eligible,
    )
    return _maybe_enqueue(
        question=question,
        response=response,
        writeback=writeback,
        wiki_store=wiki_store,
        assessment=assessment,
    )


def _maybe_enqueue(
    *,
    question: str,
    response: QueryResponse,
    writeback: str,
    wiki_store: WikiStore,
    assessment: ConfidenceAssessment | None = None,
) -> QueryResponse:
    if not response.source:
        response.trace.steps.append(
            TraceStep(kind="writeback", detail={"status": "skip-no-source"})
        )
        return response

    if writeback == "auto" and response.writeback_eligible is not True:
        response.trace.steps.append(
            TraceStep(kind="writeback", detail={"status": "skipped-ineligible"})
        )
        return response

    decision = decide(cast(WritebackFlag, writeback), is_tty=sys.stdout.isatty())
    if decision.action == "enqueue":
        try:
            result = enqueue(
                _build_queue_item(
                    question=question,
                    response=response,
                    assessment=assessment,
                ),
                paths=wiki_store.paths,
            )
        except Exception as exc:
            response.trace.steps.append(
                TraceStep(kind="writeback", detail={"status": "failed", "error": str(exc)})
            )
            raise KSError(
                "write-back enqueue 失敗",
                exit_code=ExitCode.GENERAL,
                code="WRITEBACK_FAILED",
                details=[str(exc)],
                response=response,
            ) from exc
        trace_status = {
            "created": "enqueued",
            "deduped": "enqueued-deduped",
            "already-promoted": "already-promoted",
        }[result.status]
        detail: dict[str, object] = {"status": trace_status, "id": result.id}
        if result.path is not None:
            detail["path"] = str(result.path)
        response.trace.steps.append(TraceStep(kind="writeback", detail=detail))
        if result.status == "created":
            wiki_store.append_log(
                LogEntry(
                    timestamp=utc_now_iso(),
                    event="writeback",
                    status="enqueued",
                    query=question,
                    route=response.trace.route,
                    source=response.source,
                    confidence=response.confidence,
                )
            )
        return response

    response.trace.steps.append(TraceStep(kind="writeback", detail={"status": decision.status}))
    return response


def _build_queue_item(
    *,
    question: str,
    response: QueryResponse,
    assessment: ConfidenceAssessment | None,
) -> WritebackQueueItem:
    return build_item(
        question=question,
        answer=response.answer,
        route=response.trace.route,
        source=response.source,
        evidence=response.evidence,
        retrieval_score=(
            assessment.retrieval_score if assessment is not None else response.retrieval_score
        ),
        writeback_eligible=(
            assessment.writeback_eligible
            if assessment is not None
            else bool(response.writeback_eligible)
        ),
        reasons=assessment.reasons if assessment is not None else [],
    )
