"""Unit tests for wiki candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

from hks.retrievers.wiki import collect_wiki_candidates, has_wiki_secondary_intent


def test_has_wiki_secondary_intent_accepts_summary_terms() -> None:
    assert has_wiki_secondary_intent("Atlas 摘要")
    assert has_wiki_secondary_intent("project overview")


def test_collect_wiki_returns_candidate_on_hit() -> None:
    wiki_store = MagicMock()
    page = MagicMock()
    page.title = "Atlas"
    page.summary = "Atlas project summary"
    page.body = "Atlas body"
    page.source_relpath = "atlas.md"
    page.slug = "atlas"
    wiki_store.search.return_value = page

    candidates, steps = collect_wiki_candidates("Atlas 摘要", wiki_store=wiki_store)

    assert len(candidates) == 1
    assert candidates[0].source_route == "wiki"
    assert candidates[0].metadata["source_relpath"] == "atlas.md"
    assert steps[0].kind == "wiki_lookup"
    assert steps[0].detail["hit"] is True


def test_collect_wiki_returns_empty_on_miss() -> None:
    wiki_store = MagicMock()
    wiki_store.search.return_value = None
    wiki_store.overview.return_value = None

    candidates, steps = collect_wiki_candidates("random question", wiki_store=wiki_store)

    assert candidates == []
    assert steps[0].detail["hit"] is False
