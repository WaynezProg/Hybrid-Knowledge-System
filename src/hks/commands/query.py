"""CLI entry for retrieval and optional write-back."""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from hks.core.manifest import Manifest, resume_or_rebuild, utc_now_iso
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.graph.query import answer_query
from hks.graph.store import GraphStore
from hks.page_tree.store import TreeStore
from hks.routing.router import route as route_query
from hks.routing.rules import load_rules
from hks.storage.vector import SearchHit, VectorStore
from hks.storage.wiki import LogEntry, WikiStore
from hks.writeback.gate import WritebackFlag, decide
from hks.writeback.writer import WritebackContext, commit


@dataclass(slots=True)
class Candidate:
    text: str
    source_route: Route
    score: float
    metadata: dict[str, object]


def _evidence_quote(text: object, *, limit: int = 240) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized[:limit]


def _metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    if candidate.source_route == "wiki":
        return _wiki_candidate_evidence(candidate)
    if candidate.source_route == "graph":
        return _graph_candidate_evidence(candidate)
    return _vector_candidate_evidence(candidate)


def _wiki_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = _metadata_str(candidate.metadata, "source_relpath")
    quote = _evidence_quote(candidate.metadata.get("quote") or candidate.text)
    if relpath is None or not quote:
        return []
    return [{"source_relpath": relpath, "route": "wiki", "quote": quote}]


def _graph_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpaths = candidate.metadata.get("relpaths")
    evidence_by_relpath = candidate.metadata.get("evidence_by_relpath")
    if not isinstance(relpaths, list):
        return []
    quotes = evidence_by_relpath if isinstance(evidence_by_relpath, dict) else {}
    evidence: list[dict[str, object]] = []
    seen: set[str] = set()
    for relpath in relpaths:
        if not isinstance(relpath, str) or relpath in seen:
            continue
        seen.add(relpath)
        quote = _evidence_quote(quotes.get(relpath) or candidate.text)
        if quote:
            evidence.append(
                {"source_relpath": relpath, "route": "graph", "quote": quote}
            )
    return evidence


def _vector_candidate_evidence(candidate: Candidate) -> list[dict[str, object]]:
    relpath = _metadata_str(candidate.metadata, "source_relpath")
    quote = _evidence_quote(candidate.text)
    if relpath is None or not quote:
        return []

    entry: dict[str, object] = {
        "source_relpath": relpath,
        "route": "vector",
        "quote": quote,
    }
    section_path = _metadata_str(candidate.metadata, "section_path")
    if section_path is not None:
        entry["section_path"] = section_path
    page_range = candidate.metadata.get("page_range")
    if isinstance(page_range, dict):
        entry["page_range"] = page_range
    return [entry]


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
    if _lexical_terms(question):
        return _vector_hit_lexical_score(question, hit) > 0
    return hit.similarity >= 0.2


def _vector_hit_lexical_score(question: str, hit: SearchHit) -> int:
    query_terms = _lexical_terms(question)
    text_terms = _lexical_terms(hit.text)
    return len(query_terms & text_terms)


def _choose_vector_hit(question: str, hits: list[SearchHit]) -> SearchHit | None:
    relevant_hits = [hit for hit in hits if _vector_hit_is_relevant(question, hit)]
    if not relevant_hits:
        return None
    return max(
        relevant_hits,
        key=lambda hit: (_vector_hit_lexical_score(question, hit), hit.similarity),
    )


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
    manifest: Manifest | None = None,
    tree_store: TreeStore | None = None,
) -> dict[str, object]:
    detail: dict[str, object] = {
        "top_k": top_k,
        "top_similarity": round(top_similarity, 4),
    }
    if chosen_hit is None:
        return detail
    detail["quote"] = _evidence_quote(chosen_hit.text)
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
    if manifest is not None and tree_store is not None:
        detail.update(
            _vector_section_context(
                chosen_hit=chosen_hit,
                manifest=manifest,
                tree_store=tree_store,
            )
        )
    return detail


def _vector_section_context(
    *,
    chosen_hit: SearchHit,
    manifest: Manifest,
    tree_store: TreeStore,
) -> dict[str, object]:
    relpath = chosen_hit.metadata.get("source_relpath")
    node_id = chosen_hit.metadata.get("tree_node_id")
    if not isinstance(relpath, str) or not isinstance(node_id, str):
        return {}

    entry = manifest.entries.get(relpath)
    if entry is None:
        return {}
    tree_slug = entry.derived.page_tree
    if tree_slug is None:
        return {}

    try:
        tree = tree_store.load(tree_slug)
    except Exception:
        return {}
    if tree.source_relpath != relpath or tree.source_sha256 != entry.sha256:
        return {}

    section_path = tree.section_path(node_id)
    node = next(
        (candidate for candidate in tree.flat_nodes() if candidate.node_id == node_id),
        None,
    )
    if section_path is None or node is None:
        return {}

    context: dict[str, object] = {"section_path": section_path}
    page_start = node.metadata.get("page_start")
    page_end = node.metadata.get("page_end")
    if isinstance(page_start, int) and isinstance(page_end, int):
        context["page_range"] = {"start": page_start, "end": page_end}
    return context


def _graph_trace_detail(
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


def _has_wiki_secondary_intent(question: str) -> bool:
    lowered = question.lower()
    return any(
        keyword in lowered
        for keyword in ("summary", "overview", "摘要", "總結", "重點", "說明")
    )


def _collect_wiki_candidates(
    question: str,
    *,
    wiki_store: WikiStore,
    require_secondary_intent: bool = False,
    is_primary: bool = False,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    if require_secondary_intent and not _has_wiki_secondary_intent(question):
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={"hit": False, "reason": "secondary-intent-miss"},
            )
        )
        return candidates, steps

    page = wiki_store.search(question)
    if page is not None:
        quote = _evidence_quote(page.summary or page.body)
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={
                    "slug": page.slug,
                    "hit": True,
                    "source_relpath": page.source_relpath,
                    "quote": quote,
                },
            )
        )
        candidates.append(
            Candidate(
                text=f"{page.title}: {page.summary}",
                source_route="wiki",
                score=1.0 if is_primary else 0.65,
                metadata={
                    "source_relpath": page.source_relpath,
                    "slug": page.slug,
                    "quote": quote,
                },
            )
        )
    else:
        overview = wiki_store.overview()
        if overview and _has_wiki_secondary_intent(question):
            steps.append(
                TraceStep(
                    kind="wiki_lookup",
                    detail={"slug": None, "hit": True, "mode": "overview"},
                )
            )
            candidates.append(
                Candidate(text=overview, source_route="wiki", score=0.7, metadata={})
            )
        else:
            steps.append(TraceStep(kind="wiki_lookup", detail={"hit": False}))

    return candidates, steps


def _collect_graph_candidates(
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
            detail=_graph_trace_detail(
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
                "evidence_by_relpath": evidence_by_relpath,
            },
        )
    )
    return candidates, steps


def _collect_vector_candidates(
    question: str,
    *,
    vector_store: VectorStore,
    manifest: Manifest,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    candidate_limit = max(5, min(50, vector_store.count()))
    hits = vector_store.search(question, top_k=candidate_limit)
    top_similarity = hits[0].similarity if hits else 0.0

    relevant_hits = [hit for hit in hits if _vector_hit_is_relevant(question, hit)]
    tree_store = TreeStore(vector_store.paths)

    for hit in relevant_hits[:5]:
        metadata: dict[str, object] = dict(hit.metadata)
        section_ctx = _vector_section_context(
            chosen_hit=hit, manifest=manifest, tree_store=tree_store
        )
        metadata.update(section_ctx)
        candidates.append(
            Candidate(
                text=hit.text,
                source_route="vector",
                score=hit.similarity,
                metadata=metadata,
            )
        )

    detail = _vector_trace_detail(
        top_k=candidate_limit,
        top_similarity=top_similarity,
        chosen_hit=relevant_hits[0] if relevant_hits else None,
        manifest=manifest,
        tree_store=tree_store,
    )
    steps.append(TraceStep(kind="vector_lookup", detail=detail))

    return candidates, steps


def _rrf_rerank(candidates: list[Candidate], *, k: int = 60) -> list[Candidate]:
    if not candidates:
        return []

    source_groups: dict[str, list[tuple[int, Candidate]]] = {}
    for index, candidate in enumerate(candidates):
        source_groups.setdefault(candidate.source_route, []).append((index, candidate))

    for route_candidates in source_groups.values():
        route_candidates.sort(key=lambda item: item[1].score, reverse=True)

    rrf_scores: dict[int, float] = {}
    for route_candidates in source_groups.values():
        for rank, (index, _candidate) in enumerate(route_candidates):
            rrf_scores[index] = rrf_scores.get(index, 0.0) + 1.0 / (k + rank + 1)

    ranked_indices = sorted(
        rrf_scores,
        key=lambda i: (rrf_scores[i], candidates[i].score),
        reverse=True,
    )
    return [
        Candidate(
            text=candidates[i].text,
            source_route=candidates[i].source_route,
            score=candidates[i].score,
            metadata=candidates[i].metadata,
        )
        for i in ranked_indices
    ]


def _llm_rerank(
    question: str,
    candidates: list[Candidate],
) -> list[Candidate]:
    from hks.core.config import config_value
    from hks.llm.config import hosted_provider_ready
    from hks.llm.providers import _openai_chat

    if not hosted_provider_ready("openai"):
        return _rrf_rerank(candidates)
    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if not api_key:
        return _rrf_rerank(candidates)
    endpoint = config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT") or "https://api.openai.com/v1"
    model = config_value("HKS_LLM_MODEL") or "gpt-4o-mini"

    capped = candidates[:10]
    snippet_list = "\n".join(
        f"[{i}] ({c.source_route}) {c.text[:200]}" for i, c in enumerate(capped)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a relevance ranker. Given a question and numbered text snippets, "
                "return a JSON object with a 'ranking' key containing an array of snippet "
                "indices sorted by relevance (most relevant first). "
                'Example: {"ranking": [2, 0, 1]}'
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nSnippets:\n{snippet_list}",
        },
    ]

    try:
        result = _openai_chat(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            messages=messages,
            timeout=30,
        )
        ranking = result.get("ranking", [])
        if not isinstance(ranking, list):
            return _rrf_rerank(candidates)

        ranked: list[Candidate] = []
        seen: set[int] = set()
        for idx in ranking:
            if isinstance(idx, int) and 0 <= idx < len(capped) and idx not in seen:
                seen.add(idx)
                ranked.append(
                    Candidate(
                        text=capped[idx].text,
                        source_route=capped[idx].source_route,
                        score=capped[idx].score,
                        metadata=capped[idx].metadata,
                    )
                )
        for i, c in enumerate(capped):
            if i not in seen:
                ranked.append(c)
        return ranked
    except Exception:
        return _rrf_rerank(candidates)


def _rerank_candidates(
    question: str,
    candidates: list[Candidate],
) -> tuple[list[Candidate], str]:
    from hks.llm.config import hosted_provider_ready

    if hosted_provider_ready("openai"):
        ranked = _llm_rerank(question, candidates)
        return ranked, "llm-rerank"
    ranked = _rrf_rerank(candidates)
    return ranked, "rrf"


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

    all_candidates: list[Candidate] = []

    wiki_candidates, wiki_steps = _collect_wiki_candidates(
        question,
        wiki_store=wiki_store,
        require_secondary_intent=(decision.route != "wiki"),
        is_primary=(decision.route == "wiki"),
    )
    all_candidates.extend(wiki_candidates)
    steps.extend(wiki_steps)

    graph_candidates, graph_steps = _collect_graph_candidates(question, graph_store=graph_store)
    all_candidates.extend(graph_candidates)
    steps.extend(graph_steps)

    vector_candidates, vector_steps = _collect_vector_candidates(
        question, vector_store=vector_store, manifest=manifest
    )
    all_candidates.extend(vector_candidates)
    steps.extend(vector_steps)

    if not all_candidates:
        response = _build_no_hit_response(decision.route, steps)
        return _maybe_writeback(
            question=question, response=response, writeback=writeback, wiki_store=wiki_store
        )

    ranked, strategy = _rerank_candidates(question, all_candidates)
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

    response = QueryResponse(
        answer=winner.text,
        source=[winner.source_route],
        confidence=winner.score,
        trace=Trace(route=winner.source_route, steps=steps),
        evidence=_candidate_evidence(winner),
    )
    return _maybe_writeback(
        question=question, response=response, writeback=writeback, wiki_store=wiki_store
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
