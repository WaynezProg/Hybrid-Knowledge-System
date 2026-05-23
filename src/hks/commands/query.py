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
from hks.retrievers.session_memory import (
    collect_session_memory_candidates,
    prefer_session_memory_candidates,
)
from hks.retrievers.vector import collect_vector_candidates
from hks.retrievers.wiki import collect_wiki_candidates
from hks.routing.router import route as route_query
from hks.routing.rules import load_rules
from hks.routing.session_memory import analyze_session_memory_intent
from hks.storage.vector import VectorStore
from hks.storage.wiki import LogEntry, WikiStore
from hks.writeback.gate import WritebackFlag, decide
from hks.writeback.writer import WritebackContext, commit

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
    session_intent = analyze_session_memory_intent(question)
    wiki_store = WikiStore(paths)
    graph_store = GraphStore(paths)
    vector_store = VectorStore(paths)

    all_candidates: list[Candidate] = []

    session_candidates, session_steps = collect_session_memory_candidates(
        question,
        wiki_store=wiki_store,
        intent=session_intent,
    )
    all_candidates.extend(session_candidates)
    steps.extend(session_steps)

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
        return _maybe_writeback(
            question=question, response=response, writeback=writeback, wiki_store=wiki_store
        )

    all_candidates, preferred_count = prefer_session_memory_candidates(
        all_candidates,
        session_intent,
    )
    if preferred_count:
        steps.append(
            TraceStep(
                kind="routing_model",
                detail={
                    "rule_id": "session_memory_intent",
                    "target_route": "wiki",
                    "intent": session_intent.to_detail() if session_intent else {},
                    "preferred_candidate_count": preferred_count,
                },
            )
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
        return _maybe_writeback(
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
        confidence=assessment.calibrated_confidence,
        trace=Trace(route=winner.source_route, steps=steps),
        evidence=evidence,
        retrieval_score=assessment.retrieval_score,
        calibrated_confidence=assessment.calibrated_confidence,
        writeback_eligible=assessment.writeback_eligible,
    )
    return _maybe_writeback(
        question=question,
        response=response,
        writeback=writeback,
        wiki_store=wiki_store,
        assessment=assessment,
    )


def _maybe_writeback(
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

    decision = decide(
        cast(WritebackFlag, writeback),
        assessment=assessment,
        confidence=response.confidence,
        is_tty=sys.stdout.isatty(),
    )
    if decision.action == "commit":
        try:
            context = _build_writeback_context(response, wiki_store)
            response.trace.steps.extend(
                commit(
                    query=question,
                    response=response,
                    status=decision.status,
                    context=context,
                    wiki_store=wiki_store,
                    forced=decision.forced,
                )
            )
            if decision.forced:
                _record_forced_writeback_event(question=question, response=response)
        except Exception as exc:
            response.trace.steps.append(
                TraceStep(kind="writeback", detail={"status": "failed", "error": str(exc)})
            )
            raise KSError(
                "write-back 失敗",
                exit_code=ExitCode.GENERAL,
                code="WRITEBACK_FAILED",
                details=[str(exc)],
                response=response,
            ) from exc
        return response

    if decision.status in {
        "declined",
        "auto-skipped-ineligible",
        "auto-skipped-low-confidence",
    }:
        wiki_store.append_log(
            LogEntry(
                timestamp=utc_now_iso(),
                event="writeback",
                status=decision.status,
                query=question,
                route=response.trace.route,
                source=response.source,
                confidence=response.confidence,
            )
        )
    response.trace.steps.append(TraceStep(kind="writeback", detail={"status": decision.status}))
    return response


def _record_forced_writeback_event(*, question: str, response: QueryResponse) -> None:
    try:
        from hks.coordination.store import CoordinationStore

        CoordinationStore(runtime_paths()).append_events(
            [
                {
                    "type": "forced_writeback",
                    "timestamp": utc_now_iso(),
                    "query": question,
                    "route": response.trace.route,
                    "confidence": response.confidence,
                    "calibrated_confidence": response.calibrated_confidence,
                    "writeback_eligible": response.writeback_eligible,
                }
            ]
        )
    except Exception:
        return


def _build_writeback_context(response: QueryResponse, wiki_store: WikiStore) -> WritebackContext:
    related_slugs: list[str] = []
    relpaths: list[str] = []
    for step in response.trace.steps:
        if step.kind == "wiki_lookup" and step.detail.get("hit"):
            if step.detail.get("slug"):
                related_slugs.append(cast(str, step.detail["slug"]))
            if isinstance(step.detail.get("source_relpath"), str):
                relpaths.append(cast(str, step.detail["source_relpath"]))
        if step.kind == "vector_lookup" and isinstance(step.detail.get("source_relpath"), str):
            relpaths.append(cast(str, step.detail["source_relpath"]))
        if step.kind == "graph_lookup":
            relpaths.extend(
                cast(list[str], step.detail.get("relpaths", []))
                if isinstance(step.detail.get("relpaths", []), list)
                else []
            )
    for evidence_item in response.evidence:
        if isinstance(evidence_item.get("source_relpath"), str):
            relpaths.append(cast(str, evidence_item["source_relpath"]))
    related_slugs.extend(page.slug for page in wiki_store.pages_for_source_relpaths(relpaths))
    return WritebackContext(related_slugs=sorted(dict.fromkeys(related_slugs)))
