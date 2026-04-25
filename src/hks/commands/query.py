"""CLI entry for retrieval and optional write-back."""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from typing import cast

from hks.core.manifest import resume_or_rebuild, utc_now_iso
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.graph.query import answer_query
from hks.graph.store import GraphStore
from hks.routing.router import route as route_query
from hks.routing.rules import load_rules
from hks.storage.vector import SearchHit, VectorStore
from hks.storage.wiki import LogEntry, WikiStore
from hks.writeback.gate import WritebackFlag, decide
from hks.writeback.writer import WritebackContext, commit


def _lexical_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9]{2,}", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) == 2:
            terms.add(chunk)
            continue
        terms.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return terms


def _vector_hit_is_relevant(question: str, hit: SearchHit) -> bool:
    query_terms = _lexical_terms(question)
    text_terms = _lexical_terms(hit.text)
    if query_terms:
        return bool(query_terms & text_terms)
    return hit.similarity >= 0.2


def _build_no_hit_response(route: Route, steps: list[TraceStep]) -> QueryResponse:
    return QueryResponse(
        answer="未能於現有知識中找到答案",
        source=[],
        confidence=0.0,
        trace=Trace(route=route, steps=steps),
    )


def _vector_trace_detail(
    *,
    top_k: int,
    top_similarity: float,
    chosen_hit: SearchHit | None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "top_k": top_k,
        "top_similarity": round(top_similarity, 4),
    }
    if chosen_hit is None:
        return detail
    for key in (
        "source_relpath",
        "sheet_name",
        "slide_index",
        "section_type",
        "row_index",
        "source_format",
        "ocr_confidence",
        "source_engine",
    ):
        if key in chosen_hit.metadata:
            detail[key] = chosen_hit.metadata[key]
    return detail


def _graph_trace_detail(
    *,
    relpaths: list[str],
    node_ids: list[str],
    edge_ids: list[str],
    relations: Sequence[str],
) -> dict[str, object]:
    return {
        "hit": True,
        "relpaths": relpaths,
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "relations": relations,
    }


def run(question: str, *, writeback: str = "auto") -> QueryResponse:
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

    answer = ""
    source: list[Route] = []
    confidence = 0.0
    final_route = decision.route

    if decision.route == "wiki":
        page = wiki_store.search(question)
        if page is not None:
            steps.append(
                TraceStep(
                    kind="wiki_lookup",
                    detail={"slug": page.slug, "hit": True, "source_relpath": page.source_relpath},
                )
            )
            answer = f"{page.title}: {page.summary}"
            source = ["wiki"]
            confidence = 1.0
        else:
            overview = wiki_store.overview()
            if overview and any(
                keyword in question.lower()
                for keyword in ("summary", "overview", "摘要", "總結", "重點", "說明")
            ):
                steps.append(
                    TraceStep(
                        kind="wiki_lookup",
                        detail={"slug": None, "hit": True, "mode": "overview"},
                    )
                )
                answer = overview
                source = ["wiki"]
                confidence = 1.0
            else:
                steps.append(TraceStep(kind="wiki_lookup", detail={"hit": False}))
                steps.append(
                    TraceStep(
                        kind="fallback",
                        detail={"from": "wiki", "to": "vector", "reason": "wiki-miss"},
                    )
                )
                final_route = "vector"

    if final_route == "graph" and not source:
        graph_result = answer_query(question, graph_store)
        if graph_result is not None:
            steps.append(
                TraceStep(
                    kind="graph_lookup",
                    detail=_graph_trace_detail(
                        relpaths=graph_result.relpaths,
                        node_ids=graph_result.node_ids,
                        edge_ids=graph_result.edge_ids,
                        relations=graph_result.relations,
                    ),
                )
            )
            answer = graph_result.answer
            source = ["graph"]
            confidence = graph_result.confidence
        else:
            steps.append(TraceStep(kind="graph_lookup", detail={"hit": False}))
            steps.append(
                TraceStep(
                    kind="fallback",
                    detail={"from": "graph", "to": "vector", "reason": "graph-miss"},
                )
            )
            final_route = "vector"

    if final_route == "vector" and not source:
        candidate_limit = max(5, min(50, vector_store.count()))
        hits = vector_store.search(question, top_k=candidate_limit)
        top_similarity = hits[0].similarity if hits else 0.0
        relevant_hits = [hit for hit in hits if _vector_hit_is_relevant(question, hit)]
        if relevant_hits:
            chosen_hit = relevant_hits[0]
            steps.append(
                TraceStep(
                    kind="vector_lookup",
                    detail=_vector_trace_detail(
                        top_k=candidate_limit,
                        top_similarity=top_similarity,
                        chosen_hit=chosen_hit,
                    ),
                )
            )
            answer = chosen_hit.text
            source = ["vector"]
            confidence = chosen_hit.similarity
        else:
            steps.append(
                TraceStep(
                    kind="vector_lookup",
                    detail=_vector_trace_detail(
                        top_k=candidate_limit,
                        top_similarity=top_similarity,
                        chosen_hit=None,
                    ),
                )
            )
            response = _build_no_hit_response(final_route, steps)
            response = _maybe_writeback(
                question=question,
                response=response,
                writeback=writeback,
                wiki_store=wiki_store,
            )
            return response

    response = QueryResponse(
        answer=answer,
        source=source,
        confidence=confidence,
        trace=Trace(route=final_route, steps=steps),
    )
    return _maybe_writeback(
        question=question,
        response=response,
        writeback=writeback,
        wiki_store=wiki_store,
    )


def _maybe_writeback(
    *,
    question: str,
    response: QueryResponse,
    writeback: str,
    wiki_store: WikiStore,
) -> QueryResponse:
    if not response.source:
        response.trace.steps.append(
            TraceStep(kind="writeback", detail={"status": "skip-no-source"})
        )
        return response

    decision = decide(
        cast(WritebackFlag, writeback),
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
                )
            )
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

    if decision.status in {"declined", "auto-skipped-low-confidence"}:
        wiki_store.append_log(
            LogEntry(
                timestamp=utc_now_iso(),
                event="writeback",
                status="declined",
                query=question,
                route=response.trace.route,
                source=response.source,
                confidence=response.confidence,
            )
        )
    response.trace.steps.append(TraceStep(kind="writeback", detail={"status": decision.status}))
    return response


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
    related_slugs.extend(page.slug for page in wiki_store.pages_for_source_relpaths(relpaths))
    return WritebackContext(related_slugs=sorted(dict.fromkeys(related_slugs)))
