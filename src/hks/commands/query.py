"""CLI entry for retrieval and the optional write-back review queue enqueue."""

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
from hks.retrieval.bm25 import holds_identifiers, identifier_terms
from hks.retrieval.confidence import ConfidenceAssessment, assess
from hks.retrieval.evidence import candidate_evidence
from hks.retrieval.models import Candidate
from hks.retrievers.graph import collect_graph_candidates
from hks.retrievers.lexical import collect_lexical_candidates
from hks.retrievers.page_tree import collect_page_tree_candidates
from hks.retrievers.session_memory import (
    collect_session_memory_candidates,
    collect_workspace_vector_entries,
    is_date_range_intent,
    prefer_session_memory_candidates,
    synthesize_date_range_summary,
    synthesize_workspace_status,
)
from hks.retrievers.vector import collect_vector_candidates
from hks.retrievers.wiki import collect_wiki_candidates
from hks.routing.router import route as route_query
from hks.routing.rules import load_rules
from hks.routing.session_memory import analyze_session_memory_intent
from hks.storage.vector import VectorStore
from hks.storage.wiki import EventStatus, LogEntry, WikiPage, WikiStore
from hks.writeback.gate import WritebackFlag, decide
from hks.writeback.queue import WritebackQueueItem, build_item, enqueue
from hks.writeback.writer import writeback_page_behind

_FINAL_SCORE_THRESHOLDS: dict[Route, float] = {
    "vector": 0.25,
    # Coverage of about a third of the question's rarity-weighted terms: an identifier
    # asked about in a sentence ("ERR-4012 怎麼修") passes, a different identifier that only
    # shares its prefix does not.
    "lexical": 0.3,
}
_VECTOR_PRIMARY_FINAL_SCORE_THRESHOLD = 0.2
_VECTOR_LEXICAL_FINAL_SCORE_THRESHOLD = 0.4
# A vector answer needs some evidence that it is about the question: either the embedding
# is reasonably sure, or the passage holds some of the question's rarer words. With neither
# it is only the nearest chunk of a knowledge base that has nothing on the subject.
# See specs/026-vector-evidence-gate/spec.md for how the two numbers were chosen.
_WEAK_SIMILARITY = 0.30
_WEAK_COVERAGE = 0.05


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


def _weak_evidence(candidate: Candidate, question: str) -> dict[str, float] | None:
    """The similarity and coverage of a vector answer that has too little of either.
    ``None`` when the answer may stand, or when coverage was not measured (keyword
    retrieval is off or was skipped, or the question has no word to look for), in which
    case nothing is taken away."""
    if candidate.source_route != "vector":
        return None
    if identifier_terms(question):
        # It got here past the identifier filter, so it names what was asked for: that is
        # evidence, however many other words the question wraps around the identifier.
        return None
    similarity = candidate.metadata.get("vector_similarity")
    coverage = candidate.metadata.get("query_coverage")
    if not isinstance(similarity, int | float) or not isinstance(coverage, int | float):
        return None
    if similarity < _WEAK_SIMILARITY and coverage < _WEAK_COVERAGE:
        return {"vector_similarity": round(float(similarity), 4), "query_coverage": float(coverage)}
    return None


def _passes_final_score_gate(
    candidate: Candidate,
    *,
    requested_route: Route | None = None,
) -> bool:
    return candidate.score >= _final_score_threshold(
        candidate,
        requested_route=requested_route,
    )


def _identifier_text(candidate: Candidate) -> str:
    """What a candidate is checked against: the whole chunk or page, not just the excerpt."""
    whole = candidate.metadata.get("_hks_match_text")
    quote = candidate.metadata.get("quote")
    parts = [candidate.text, whole if isinstance(whole, str) else "", str(quote or "")]
    return "\n".join(parts)


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

    graph_candidates, graph_steps = collect_graph_candidates(question, graph_store=graph_store)
    all_candidates.extend(graph_candidates)
    steps.extend(graph_steps)

    vector_candidates, vector_steps = collect_vector_candidates(
        question, vector_store=vector_store, manifest=manifest
    )
    all_candidates.extend(vector_candidates)
    steps.extend(vector_steps)

    lexical_candidates, lexical_steps = collect_lexical_candidates(
        question,
        vector_store=vector_store,
        manifest=manifest,
        vector_candidates=vector_candidates,
    )
    all_candidates.extend(lexical_candidates)
    steps.extend(lexical_steps)

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

    if (
        session_intent is not None
        and session_intent.is_status_query
        and session_intent.workspace is not None
    ):
        workspace_entries = collect_workspace_vector_entries(
            vector_store=vector_store,
            intent=session_intent,
        )
        status_candidate = synthesize_workspace_status(workspace_entries, session_intent)
        if status_candidate is not None:
            steps.append(
                TraceStep(
                    kind="workspace_status_synthesis",
                    detail={
                        "workspace": session_intent.workspace,
                        "entry_count": status_candidate.metadata.get("entry_count"),
                        "latest_date": status_candidate.metadata.get("latest_date"),
                    },
                )
            )
            evidence = candidate_evidence(status_candidate)
            assessment = ConfidenceAssessment(
                retrieval_score=status_candidate.score,
                confidence=status_candidate.score,
                writeback_eligible=False,
                auto_threshold=999.0,
                reasons=["workspace status synthesis is not auto-writeback eligible"],
            )
            response = QueryResponse(
                answer=status_candidate.text,
                source=[status_candidate.source_route],
                confidence=assessment.confidence,
                trace=Trace(route=status_candidate.source_route, steps=steps),
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

    if session_intent is not None and is_date_range_intent(session_intent):
        range_candidates = list(session_candidates)
        if session_intent.workspace:
            vector_candidates = collect_workspace_vector_entries(
                vector_store=vector_store,
                intent=session_intent,
            )
            if vector_candidates:
                range_candidates = vector_candidates
        range_summary = synthesize_date_range_summary(range_candidates, session_intent)
        if range_summary is not None:
            steps.append(
                TraceStep(
                    kind="date_range_synthesis",
                    detail={
                        "date_start": session_intent.date_start,
                        "date_end": session_intent.date_end,
                        "entry_count": range_summary.metadata.get("entry_count"),
                        "source_relpaths": range_summary.metadata.get("source_relpaths"),
                    },
                )
            )
            evidence = candidate_evidence(range_summary)
            assessment = ConfidenceAssessment(
                retrieval_score=range_summary.score,
                confidence=range_summary.score,
                writeback_eligible=False,
                auto_threshold=999.0,
                reasons=["date range synthesis is not auto-writeback eligible"],
            )
            response = QueryResponse(
                answer=range_summary.text,
                source=[range_summary.source_route],
                confidence=assessment.confidence,
                trace=Trace(route=range_summary.source_route, steps=steps),
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

    # A question that names a specific thing (a ticket, a version, a file) is answered only
    # by content that mentions it. Related content about another ticket is not an answer.
    identifiers = identifier_terms(question)
    candidate_total = len(all_candidates)
    all_candidates = [
        candidate
        for candidate in all_candidates
        if holds_identifiers(identifiers, _identifier_text(candidate))
    ]
    identifier_filtered = candidate_total - len(all_candidates)
    if not all_candidates:
        steps.append(
            TraceStep(
                kind="fallback",
                detail={
                    "status": "no-hit",
                    "reason": "identifier_not_found",
                    "identifiers": sorted(identifiers),
                    "candidates_dropped": identifier_filtered,
                },
            )
        )
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
                "identifier_filtered": identifier_filtered,
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

    # Only an answer that passed the score gate is looked at again, so the reason an
    # answer was already refused for stays the same.
    weak = _weak_evidence(winner, question)
    if weak is not None:
        steps.append(
            TraceStep(
                kind="fallback",
                detail={
                    "status": "no-hit",
                    "reason": "weak_evidence",
                    "route": winner.source_route,
                    **weak,
                    "thresholds": {
                        "vector_similarity": _WEAK_SIMILARITY,
                        "query_coverage": _WEAK_COVERAGE,
                    },
                },
            )
        )
        return _maybe_enqueue(
            question=question,
            response=_build_no_hit_response(decision.route, steps),
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


_ENQUEUE_TRACE_STATUS = {
    "created": "enqueued",
    "deduped": "enqueued-deduped",
    "already-promoted": "already-promoted",
}


def _maybe_enqueue(
    *,
    question: str,
    response: QueryResponse,
    writeback: str,
    wiki_store: WikiStore,
    assessment: ConfidenceAssessment | None = None,
) -> QueryResponse:
    """Put the answer up for review when the caller asked for write-back.

    A query never writes a wiki page: ``ks writeback approve`` is the only way in. An
    answer that was refused (no candidate, the score gate, the vector evidence gate) has
    no source and is never enqueued, whatever the flag.
    """
    if not response.source:
        response.trace.steps.append(
            TraceStep(kind="writeback", detail={"status": "skip-no-source"})
        )
        return response

    if writeback == "auto" and response.writeback_eligible is not True:
        # Kept in wiki/log.md (spec 021) so a skipped auto enqueue can be looked into later.
        _append_writeback_log(wiki_store, question, response, "auto-skipped-ineligible")
        response.trace.steps.append(
            TraceStep(kind="writeback", detail={"status": "auto-skipped-ineligible"})
        )
        return response

    if writeback != "no":
        promoted = _answered_from_writeback_page(question, response, wiki_store)
        if promoted is not None:
            response.trace.steps.append(TraceStep(kind="writeback", detail=promoted))
            return response

    decision = decide(cast(WritebackFlag, writeback), is_tty=sys.stdout.isatty())
    if decision.action != "enqueue":
        # ``--writeback=no`` asks for nothing to be written: no queue item and no entry in
        # wiki/log.md, only the writeback step in the trace. A declined ``ask`` is a
        # decision somebody made, so it is still logged.
        if writeback != "no" and decision.status == "declined":
            _append_writeback_log(wiki_store, question, response, "declined")
        response.trace.steps.append(
            TraceStep(kind="writeback", detail={"status": decision.status})
        )
        return response

    try:
        result = enqueue(
            _build_queue_item(question=question, response=response, assessment=assessment),
            paths=wiki_store.paths,
        )
        if result.status == "created":
            _append_writeback_log(wiki_store, question, response, "enqueued")
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
    detail: dict[str, object] = {
        "status": _ENQUEUE_TRACE_STATUS[result.status],
        "id": result.id,
    }
    if result.path is not None:
        detail["path"] = result.path.relative_to(wiki_store.paths.root).as_posix()
    response.trace.steps.append(TraceStep(kind="writeback", detail=detail))
    return response


def _answered_from_writeback_page(
    question: str,
    response: QueryResponse,
    wiki_store: WikiStore,
) -> dict[str, object] | None:
    """The trace detail for an answer that was read from a writeback page, else ``None``.

    Such an answer is an earlier approved answer coming back, not new knowledge: asking the
    same question again must not put it up for review a second time, and another question
    answered by it must not be promoted into a page that only cites that page's summary.
    """
    if response.trace.route != "wiki":
        return None
    pages = wiki_store.list_pages()
    behind = [writeback_page_behind(wiki_store, item, pages=pages) for item in response.evidence]
    if not behind or any(page is None for page in behind):
        return None
    page = cast(WikiPage, behind[0])
    same_question = page.metadata.get("writeback_query", "").strip() == question.strip()
    return {
        "status": "already-promoted" if same_question else "skipped-derived-answer",
        "slug": page.slug,
        "path": f"pages/{page.slug}.md",
        "source_relpath": page.source_relpath,
    }


def _append_writeback_log(
    wiki_store: WikiStore,
    question: str,
    response: QueryResponse,
    status: EventStatus,
) -> None:
    wiki_store.append_log(
        LogEntry(
            timestamp=utc_now_iso(),
            event="writeback",
            status=status,
            query=question,
            route=response.trace.route,
            source=response.source,
            confidence=response.confidence,
        )
    )


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
