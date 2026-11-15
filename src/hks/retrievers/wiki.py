"""Wiki candidate retrieval."""

from __future__ import annotations

import math
import re

from hks.core.schema import TraceStep
from hks.errors import KSError
from hks.retrieval.bm25 import lexical_tokens
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.routing.rules import load_rules
from hks.storage.wiki import WikiPage, WikiStore

_INTENT_KEYWORDS = ("summary", "overview", "摘要", "總結", "重點", "說明")
# A page that passes keeps at least this share of the route's score; the rest follows how
# much of the question it holds.
_RELEVANCE_FLOOR = 0.7

# Words that give a question its shape and say nothing about its subject. A page that
# shares only these with the question is not about it: "When is the Atlas migration
# scheduled" and a page titled "What risk does the Bolt cache have" share "the";
# 「Atlas 遷移做了什麼」 and 「Bolt 快取做了什麼」 share 「做了什麼」. Pages approved from the
# write-back queue are titled with the question that produced them, so they hold such
# words more than ingested pages do.
_QUESTION_WORDS_EN = frozenset(
    """
    an the is are was were be been am do does did has have had what when where which who
    whom whose why how of to in on at for from by with about as and or but if it its this
    that these those there their they we you my our your me us can could should would will
    shall may might not no any some all so than then
    """.split()
)
_QUESTION_PHRASES_ZH = tuple(
    sorted(
        """
        為什麼 为什么 做了什麼 做了什么 是什麼 是什么 有什麼 有什么 什麼時候 什么时候 什麼 什么
        做了 有哪些 哪些 哪個 哪个 哪裡 哪里 如何 怎麼 怎么 怎樣 怎样 是否 是誰 是谁 多少 幾個
        几个 有沒有 有没有 請問 请问 嗎 吗 呢
        """.split(),
        key=len,
        reverse=True,
    )
)
_ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,}(?![A-Za-z0-9])")


def has_wiki_secondary_intent(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in _INTENT_KEYWORDS)


def _answer_kind_words() -> tuple[str, ...]:
    """Words that say what kind of answer is wanted, not what it is about: the ones above
    and whatever the routing rules send to the wiki route ("summarize", "概述")."""
    words = set(_INTENT_KEYWORDS)
    try:
        for rule in load_rules().rules:
            if rule.target_route == "wiki":
                words.update(word.lower() for word in (*rule.keywords_zh, *rule.keywords_en))
    except KSError:
        pass
    return tuple(sorted(words, key=len, reverse=True))


def _without_answer_kind_words(lowered: str) -> str:
    for word in _answer_kind_words():
        if word.isascii():
            # Whole words only: "summary" inside "SummaryStore" is part of a name.
            lowered = re.sub(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", " ", lowered)
        else:
            lowered = lowered.replace(word, " ")
    return lowered


def _page_text(page: WikiPage) -> str:
    return "\n".join((page.title, page.slug.replace("-", " "), page.summary, page.body))


def _coverage(terms: set[str], present: set[str], document_sets: list[set[str]]) -> float:
    """Share of ``terms`` in ``present``, each weighted by its rarity across the pages."""
    total = len(document_sets)
    matched = weight = 0.0
    for term in terms:
        containing = sum(1 for held in document_sets if term in held)
        idf = math.log(1.0 + (total - containing + 0.5) / (containing + 0.5))
        weight += idf
        if term in present:
            matched += idf
    return matched / weight if weight else 0.0


def wiki_page_relevance(question: str, page: WikiPage, pages: list[WikiPage]) -> float | None:
    """Share (0..1) of the question's terms the page holds, rare terms weighing more.

    Words that only say what kind of answer is wanted need not be in the page: the better
    of the two readings counts, so a page titled "architecture summary" is still a fair
    answer to "summary ...". ``None`` when the question leaves nothing to compare (a single
    character, or only such a word): then there is no ground to call the page unrelated.
    """
    asked = question.lower()
    subject = set(lexical_tokens(_without_answer_kind_words(asked)))
    if not subject:
        return None
    document_sets = [set(lexical_tokens(_page_text(one))) for one in pages]
    present = set(lexical_tokens(_page_text(page)))
    whole = set(lexical_tokens(asked))
    relevance = _coverage(subject, present, document_sets)
    if whole != subject:
        relevance = max(relevance, _coverage(whole, present, document_sets))
    return relevance


def subject_terms(question: str) -> set[str]:
    """The question's terms without its question words. A word written in capitals ("IT",
    "US") is a name, not a question word. Words that ask for a kind of answer ("summary")
    stay: a page titled "architecture summary" is a fair answer to "summary ..." (024)."""
    lowered = question.lower()
    for phrase in _QUESTION_PHRASES_ZH:
        lowered = lowered.replace(phrase, " ")
    names = {word.lower() for word in _ACRONYM_RE.findall(question)}
    return {
        term for term in lexical_tokens(lowered) if term not in _QUESTION_WORDS_EN or term in names
    }


def shares_subject(question: str, page: WikiPage) -> bool:
    """Whether the page holds any term of the question other than its question words. True
    when the question has no other term: then there is no ground to call the page
    unrelated."""
    terms = subject_terms(question)
    if not terms:
        return True
    present = set(lexical_tokens(_page_text(page)))
    return not terms.isdisjoint(present)


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

    pages = wiki_store.list_pages()
    page = wiki_store.search(question, pages=pages)
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

    relevance: float | None = None
    if page is not None:
        relevance = wiki_page_relevance(question, page, pages)
        if relevance is not None:
            relevance = round(relevance, 4)
        # Not one term of the question is in the page: the page search matched a
        # substring ("and" inside "Candidate"). Or the only terms they share are question
        # words ("the", 「做了什麼」), which every question-titled page holds. Such a page
        # is not offered.
        if relevance == 0.0 or (relevance is not None and not shares_subject(question, page)):
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
        share = 1.0 if relevance is None else relevance
        score = round(base * (_RELEVANCE_FLOOR + (1.0 - _RELEVANCE_FLOOR) * share), 4)
        found: dict[str, object] = {
            "slug": page.slug,
            "hit": True,
            "source_relpath": page.source_relpath,
            "quote": quote,
        }
        if relevance is not None:
            found["relevance"] = relevance
        steps.append(
            TraceStep(
                kind="wiki_lookup",
                detail=found,
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
