"""Wiki candidate retrieval."""

from __future__ import annotations

import re

from hks.core.schema import TraceStep
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.storage.wiki import WikiPage, WikiStore


def has_wiki_secondary_intent(question: str) -> bool:
    lowered = question.lower()
    return any(
        keyword in lowered
        for keyword in ("summary", "overview", "摘要", "總結", "重點", "說明")
    )


def has_direct_wiki_page_match(question: str, page: WikiPage) -> bool:
    terms = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", question.casefold())
    if not terms:
        return False
    source_stem = page.source_relpath.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    page_identity = " ".join(
        (
            page.title,
            page.slug.replace("-", " "),
            source_stem.replace("-", " "),
        )
    ).casefold()
    return any(term in page_identity for term in terms)


def collect_wiki_candidates(
    question: str,
    *,
    wiki_store: WikiStore,
    require_secondary_intent: bool = False,
    is_primary: bool = False,
) -> tuple[list[Candidate], list[TraceStep]]:
    steps: list[TraceStep] = []
    candidates: list[Candidate] = []

    page = wiki_store.search(question)
    if (
        require_secondary_intent
        and not has_wiki_secondary_intent(question)
        and (page is None or not has_direct_wiki_page_match(question, page))
    ):
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={"hit": False, "reason": "secondary-intent-miss"},
            )
        )
        return candidates, steps

    if page is not None:
        quote = evidence_quote(page.summary or page.body)
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
        if overview and has_wiki_secondary_intent(question):
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
