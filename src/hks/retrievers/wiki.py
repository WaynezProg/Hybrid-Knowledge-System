"""Wiki candidate retrieval."""

from __future__ import annotations

import re

from hks.core.schema import TraceStep
from hks.retrieval.bm25 import query_coverage
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.storage.wiki import WikiPage, WikiStore

_INTENT_KEYWORDS = ("summary", "overview", "摘要", "總結", "重點", "說明")
# A page that holds less than this share of the question's terms was found by accident
# (the page search matches substrings: "and" inside "Candidate") and is not offered.
_MIN_RELEVANCE = 0.15
# A page that does pass keeps at least this share of the route's score; the rest follows
# how much of the question it holds.
_RELEVANCE_FLOOR = 0.7


def has_wiki_secondary_intent(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in _INTENT_KEYWORDS)


def _page_text(page: WikiPage) -> str:
    return "\n".join((page.title, page.slug.replace("-", " "), page.summary, page.body))


def wiki_page_relevance(question: str, page: WikiPage, pages: list[WikiPage]) -> float:
    """Share (0..1) of the question's terms the page holds, rare terms weighing more.

    Words that only say what kind of answer is wanted ("summary", "摘要") need not be in
    the page for it to be the page asked about.
    """
    texts = [_page_text(one) for one in pages]
    asked = question.lower()
    whole = query_coverage(asked, _page_text(page), texts)
    for keyword in _INTENT_KEYWORDS:
        asked = asked.replace(keyword, " ")
    # The better of the two readings: a page titled "architecture summary" is also a fair
    # answer to "summary ...".
    return max(whole, query_coverage(asked, _page_text(page), texts))


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

    relevance = 0.0
    if page is not None:
        relevance = round(wiki_page_relevance(question, page, wiki_store.list_pages()), 4)
        if relevance < _MIN_RELEVANCE:
            steps.append(
                TraceStep(
                    kind="wiki_lookup",
                    detail={
                        "hit": False,
                        "reason": "low-relevance",
                        "slug": page.slug,
                        "relevance": relevance,
                    },
                )
            )
            return candidates, steps

    if page is not None:
        quote = evidence_quote(page.summary or page.body)
        base = 1.0 if is_primary else 0.65
        score = round(base * (_RELEVANCE_FLOOR + (1.0 - _RELEVANCE_FLOOR) * relevance), 4)
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail={
                    "slug": page.slug,
                    "hit": True,
                    "source_relpath": page.source_relpath,
                    "quote": quote,
                    "relevance": relevance,
                },
            )
        )
        candidates.append(
            Candidate(
                text=f"{page.title}: {page.summary}",
                source_route="wiki",
                score=score,
                metadata={
                    "source_relpath": page.source_relpath,
                    "slug": page.slug,
                    "quote": quote,
                    "_hks_match_text": f"{page.title}\n{page.summary}\n{page.body}",
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
