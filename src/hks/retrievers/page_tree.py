"""Page-tree candidate retrieval."""

from __future__ import annotations

from hks.core.manifest import Manifest
from hks.core.schema import TraceStep
from hks.page_tree.model import TreeNode
from hks.page_tree.store import TreeStore
from hks.retrieval.models import Candidate
from hks.retrievers.vector import lexical_terms


def page_tree_node_score(question: str, node: TreeNode) -> float:
    """Score a page-tree node's relevance to the question using term overlap."""
    query_terms = lexical_terms(question)
    if not query_terms:
        return 0.0
    title_overlap = len(query_terms & lexical_terms(node.title))
    summary_overlap = len(query_terms & lexical_terms(node.summary)) if node.summary else 0
    return title_overlap * 2.0 + summary_overlap * 1.0


def collect_page_tree_candidates(
    question: str,
    *,
    tree_store: TreeStore,
    manifest: Manifest,
) -> tuple[list[Candidate], list[TraceStep]]:
    """Collect candidates from page-tree node titles and summaries."""
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    for entry in manifest.entries.values():
        tree_slug = entry.derived.page_tree
        if tree_slug is None:
            continue
        try:
            tree = tree_store.load(tree_slug)
        except Exception:
            continue

        for node in tree.flat_nodes():
            if not node.summary:
                continue
            score = page_tree_node_score(question, node)
            if score <= 0:
                continue
            text = node.summary
            section_path = tree.section_path(node.node_id)
            node_metadata: dict[str, object] = {
                "source_relpath": tree.source_relpath,
                "node_id": node.node_id,
                "section_path": section_path,
            }
            page_start = node.metadata.get("page_start")
            page_end = node.metadata.get("page_end")
            if isinstance(page_start, int) and isinstance(page_end, int):
                node_metadata["page_range"] = {"start": page_start, "end": page_end}
            candidates.append(
                Candidate(
                    text=text,
                    source_route="page_tree",
                    score=min(score / 10.0, 0.85),
                    metadata=node_metadata,
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    candidates = candidates[:5]

    hit = len(candidates) > 0
    steps.append(
        TraceStep(
            kind="page_tree_lookup",
            detail={"hit": hit, "candidate_count": len(candidates)},
        )
    )
    return candidates, steps
