"""Vector candidate retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

from hks.core.config import config_value
from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.core.text_models import simple_tokenize
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore
from hks.retrieval.bm25 import bm25_rank
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.storage.vector import SearchHit, VectorStore

_LEXICAL_SCORE_BONUS = 0.08
_MAX_LEXICAL_SCORE_BONUS = 0.24
_PASSAGE_MAX_TOKENS = 96
_CANDIDATE_LIMIT = 5
_LEXICAL_TOP_K = 20
_RRF_K = 60
_DEFAULT_HYBRID_MAX_CHUNKS = 20000
_PASSAGE_SPLIT_RE = re.compile(r"(?<!\d\.)(?<=[.!?。！？])\s*")


def lexical_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9]{2,}", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) == 2:
            terms.add(chunk)
            continue
        terms.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return terms


def vector_hit_is_relevant(question: str, hit: SearchHit) -> bool:
    return hit.similarity >= 0.0


def vector_hit_lexical_score(question: str, hit: SearchHit) -> int:
    query_terms = lexical_terms(question)
    text_terms = lexical_terms(hit.text)
    return len(query_terms & text_terms)


def vector_hit_final_score(question: str, hit: SearchHit) -> float:
    lexical_bonus = min(
        vector_hit_lexical_score(question, hit) * _LEXICAL_SCORE_BONUS,
        _MAX_LEXICAL_SCORE_BONUS,
    )
    return min(1.0, hit.similarity + lexical_bonus)


def best_vector_passage(
    question: str,
    text: str,
    *,
    max_tokens: int = _PASSAGE_MAX_TOKENS,
) -> str:
    passages = [passage.strip() for passage in _PASSAGE_SPLIT_RE.split(text) if passage.strip()]
    if not passages:
        return _trim_passage_tokens(text, max_tokens=max_tokens)

    query_terms = lexical_terms(question)
    best = max(
        passages,
        key=lambda passage: (
            len(query_terms & lexical_terms(passage)),
            -len(simple_tokenize(passage)),
        ),
    )
    if query_terms and not query_terms & lexical_terms(best):
        return _trim_passage_tokens(text, max_tokens=max_tokens)
    return _trim_passage_tokens(best, max_tokens=max_tokens)


def _trim_passage_tokens(text: str, *, max_tokens: int) -> str:
    tokens = simple_tokenize(text)
    if len(tokens) <= max_tokens:
        return text
    return " ".join(tokens[:max_tokens]).strip()


def choose_vector_hit(question: str, hits: list[SearchHit]) -> SearchHit | None:
    if not hits:
        return None
    return max(
        hits,
        key=lambda hit: (
            vector_hit_final_score(question, hit),
            vector_hit_lexical_score(question, hit),
            hit.similarity,
        ),
    )


def vector_trace_detail(
    *,
    question: str,
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
    passage_text = best_vector_passage(question, chosen_hit.text)
    detail["quote"] = evidence_quote(passage_text)
    detail["lexical_overlap"] = vector_hit_lexical_score(question, chosen_hit)
    detail["vector_similarity"] = round(chosen_hit.similarity, 4)
    detail["final_score"] = round(vector_hit_final_score(question, chosen_hit), 4)
    for key in (
        "source_relpath",
        "sheet_name",
        "slide_index",
        "section_type",
        "row_index",
        "source_format",
        "ocr_confidence",
        "source_engine",
        "hks_type",
        "date",
        "source_domain",
        "generator",
        "workspace_id",
        "memory_kind",
        "tool",
        "session_id",
        "evidence_id",
    ):
        if key in chosen_hit.metadata:
            detail[key] = chosen_hit.metadata[key]
    if manifest is not None and tree_store is not None:
        detail.update(
            vector_section_context(
                chosen_hit=chosen_hit,
                manifest=manifest,
                tree_store=tree_store,
                passage_text=passage_text,
            )
        )
    return detail


def vector_section_context(
    *,
    chosen_hit: SearchHit,
    manifest: Manifest,
    tree_store: TreeStore,
    passage_text: str | None = None,
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

    node = _node_for_passage(tree, passage_text) or next(
        (candidate for candidate in tree.flat_nodes() if candidate.node_id == node_id),
        None,
    )
    section_path = tree.section_path(node.node_id) if node is not None else None
    if section_path is None or node is None:
        return {}

    context: dict[str, object] = {"section_path": section_path}
    page_start = node.metadata.get("page_start")
    page_end = node.metadata.get("page_end")
    if isinstance(page_start, int) and isinstance(page_end, int):
        context["page_range"] = {"start": page_start, "end": page_end}
    return context


def _node_for_passage(tree: PageTree, passage_text: str | None) -> TreeNode | None:
    if not passage_text:
        return None
    lowered = passage_text.casefold()
    matches = [
        node
        for node in tree.flat_nodes()
        if node.title and node.title.casefold() in lowered
    ]
    if not matches:
        return None
    return max(matches, key=lambda node: (node.level, len(node.title)))


@dataclass(slots=True)
class RankedHit:
    hit: SearchHit
    dense_rank: int | None = None
    lexical_rank: int | None = None
    bm25_score: float = 0.0

    @property
    def fused_score(self) -> float:
        return sum(
            1.0 / (_RRF_K + rank) for rank in (self.dense_rank, self.lexical_rank) if rank
        )


def hybrid_search_mode() -> str:
    """``route`` (default): keyword matches the embedding did not bring up are a route of
    their own. ``fused``: BM25 joins the dense ranking inside the vector route. ``off``:
    dense only."""
    value = (config_value("HKS_HYBRID_SEARCH") or "route").strip().lower()
    if value in {"0", "false", "no", "off"}:
        return "off"
    return "fused" if value in {"fused", "1", "true", "yes", "on"} else "route"


def hybrid_max_chunks() -> int:
    try:
        return int(config_value("HKS_HYBRID_MAX_CHUNKS") or _DEFAULT_HYBRID_MAX_CHUNKS)
    except ValueError:
        return _DEFAULT_HYBRID_MAX_CHUNKS


def hybrid_rank(
    question: str,
    dense_hits: list[SearchHit],
    *,
    vector_store: VectorStore,
) -> tuple[list[RankedHit], dict[str, object]]:
    """Fuse the dense ranking with a BM25 keyword ranking of every chunk (RRF).

    A chunk the embedding ranked low, or not at all, still becomes a candidate when it
    holds the words asked for: exact names, ids and codes. Scores keep their meaning
    (similarity plus overlap bonus); only which chunks are considered changes.
    """
    ranked = {
        hit.chunk_id: RankedHit(hit, dense_rank=rank)
        for rank, hit in enumerate(dense_hits, start=1)
    }
    if hybrid_search_mode() != "fused":
        return list(ranked.values()), {"retrieval_mode": "dense"}
    chunk_count = vector_store.count()
    if chunk_count > hybrid_max_chunks():
        return list(ranked.values()), {
            "retrieval_mode": "dense",
            "lexical_skipped": "chunk_count_above_limit",
        }

    corpus = vector_store.all_chunks()
    matches = bm25_rank(question, [chunk.text for chunk in corpus], top_k=_LEXICAL_TOP_K)
    matched_ids = [corpus[index].chunk_id for index, _ in matches]
    missing = [chunk_id for chunk_id in matched_ids if chunk_id not in ranked]
    similarities = vector_store.similarities(question, missing) if missing else {}
    for rank, (index, score) in enumerate(matches, start=1):
        chunk = corpus[index]
        item = ranked.get(chunk.chunk_id)
        if item is None:
            chunk.similarity = similarities.get(chunk.chunk_id, 0.0)
            item = ranked[chunk.chunk_id] = RankedHit(chunk)
        item.lexical_rank = rank
        item.bm25_score = score

    ordered = sorted(
        ranked.values(),
        key=lambda item: (
            -item.fused_score,
            -vector_hit_final_score(question, item.hit),
            item.hit.chunk_id,
        ),
    )
    return ordered, {
        "retrieval_mode": "hybrid",
        "lexical_candidate_count": len(matches),
        "lexical_only_count": len(missing),
    }


def collect_vector_candidates(
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

    ranked, hybrid_detail = hybrid_rank(question, hits, vector_store=vector_store)
    selected = ranked[:_CANDIDATE_LIMIT]
    hits = [item.hit for item in ranked]

    tree_store = TreeStore(vector_store.paths)

    for item in selected:
        hit = item.hit
        passage_text = best_vector_passage(question, hit.text)
        metadata: dict[str, object] = dict(hit.metadata)
        metadata["chunk_id"] = hit.chunk_id
        metadata["lexical_overlap"] = vector_hit_lexical_score(question, hit)
        metadata["vector_similarity"] = hit.similarity
        metadata["final_score"] = vector_hit_final_score(question, hit)
        if item.dense_rank is not None:
            metadata["dense_rank"] = item.dense_rank
        if item.lexical_rank is not None:
            metadata["lexical_rank"] = item.lexical_rank
            metadata["bm25_score"] = round(item.bm25_score, 4)
        section_ctx = vector_section_context(
            chosen_hit=hit,
            manifest=manifest,
            tree_store=tree_store,
            passage_text=passage_text,
        )
        metadata.update(section_ctx)
        candidates.append(
            Candidate(
                text=passage_text,
                source_route="vector",
                score=vector_hit_final_score(question, hit),
                metadata=metadata,
            )
        )

    detail = vector_trace_detail(
        question=question,
        top_k=candidate_limit,
        top_similarity=top_similarity,
        chosen_hit=choose_vector_hit(question, hits),
        manifest=manifest,
        tree_store=tree_store,
    )
    detail.update(hybrid_detail)
    steps.append(TraceStep(kind="vector_lookup", detail=detail))

    return candidates, steps
