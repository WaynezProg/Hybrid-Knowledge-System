"""CLI entry for retrieval and optional write-back."""

from __future__ import annotations

import re
import sys
from typing import cast

from hks.core.manifest import resume_or_rebuild, utc_now_iso
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.routing.router import route as route_query
from hks.routing.rules import load_rules
from hks.storage.vector import SearchHit, VectorStore
from hks.storage.wiki import LogEntry, WikiStore
from hks.writeback.gate import WritebackFlag, decide
from hks.writeback.writer import commit


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


def run(question: str, *, writeback: str = "ask") -> QueryResponse:
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
    vector_store = VectorStore(paths)

    answer = ""
    source: list[Route] = []
    confidence = 0.0
    final_route = decision.route

    if decision.route == "wiki":
        page = wiki_store.search(question)
        if page is not None:
            steps.append(TraceStep(kind="wiki_lookup", detail={"slug": page.slug, "hit": True}))
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

    if final_route == "vector" and not source:
        candidate_limit = max(5, min(50, vector_store.count()))
        hits = vector_store.search(question, top_k=candidate_limit)
        top_similarity = hits[0].similarity if hits else 0.0
        relevant_hits = [hit for hit in hits if _vector_hit_is_relevant(question, hit)]
        steps.append(
            TraceStep(
                kind="vector_lookup",
                detail={"top_k": candidate_limit, "top_similarity": round(top_similarity, 4)},
            )
        )
        if relevant_hits:
            chosen_hit = relevant_hits[0]
            answer = chosen_hit.text
            source = ["vector"]
            confidence = chosen_hit.similarity
        else:
            response = _build_no_hit_response(final_route, steps)
            response = _maybe_writeback(
                question=question,
                response=response,
                writeback=writeback,
                wiki_store=wiki_store,
            )
            return response

    if decision.phase2_note and source:
        answer = f"{answer.rstrip()} 深度關係推理將於 Phase 2 支援。"

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

    decision = decide(cast(WritebackFlag, writeback), is_tty=sys.stdout.isatty())
    if decision.action == "commit":
        try:
            response.trace.steps.extend(
                commit(query=question, response=response, wiki_store=wiki_store)
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

    if decision.status == "declined":
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
