"""024：wiki 候選的分數隨頁面與問句的吻合程度變動，吻合太少的頁面不成為候選。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.core.schema import validate
from hks.retrievers.wiki import collect_wiki_candidates, wiki_page_relevance
from hks.storage.wiki import WikiPage

DOCS = {
    "memory-candidate.md": "# Memory Candidate\n\nNo candidates.\n",
    "testing-framework.md": (
        "# Agent testing\n\nBuild agent security and capability testing framework：新增 12 個"
        "檢查項目，涵蓋權限邊界與工具呼叫。\n"
    ),
    "project-atlas.md": (
        "# Project Atlas\n\nProject Atlas 目前處於設計收斂階段。主要風險是供應商交期延遲"
        "與 API 規格尚未凍結。\n"
    ),
}


def _page(slug: str, title: str, body: str) -> WikiPage:
    return WikiPage(
        slug=slug,
        title=title,
        summary=body,
        body=body,
        source_relpath=f"{slug}.md",
        origin="ingest",
        updated_at="2026-11-14T00:00:00+00:00",
    )


PAGES = [
    _page("memory-candidate", "Memory Candidate", "No candidates."),
    _page("project-atlas", "Project Atlas", "主要風險是供應商交期延遲與 API 規格尚未凍結。"),
    _page("ops-status", "Ops status", "checkout service latency is stable."),
]


@pytest.mark.contract
def test_relevance_counts_whole_terms_and_ignores_answer_kind_words() -> None:
    junk, atlas, _ = PAGES

    assert wiki_page_relevance("agent security and capability testing", junk, PAGES) == 0.0
    assert wiki_page_relevance("Project Atlas", atlas, PAGES) == pytest.approx(1.0)
    assert wiki_page_relevance("Project Atlas 摘要", atlas, PAGES) == pytest.approx(1.0)
    partial = wiki_page_relevance("Project Atlas 的負責人是誰", atlas, PAGES)
    assert partial is not None and 0.0 < partial < 1.0


@pytest.mark.contract
def test_answer_kind_words_follow_the_routing_rules_and_spare_names() -> None:
    atlas = PAGES[1]
    store = _page("store", "Store", "Generic storage notes.")
    pages = [*PAGES, store]

    # "summarize" and "概述" come from the routing rules, like "summary".
    for wording in ("summary Project Atlas", "summarize Project Atlas", "Project Atlas 概述"):
        assert wiki_page_relevance(wording, atlas, pages) == pytest.approx(1.0), wording
    # "summary" inside a name is part of the name: the Store page does not hold it.
    named = wiki_page_relevance("summary SummaryStore", store, pages)
    assert named is not None and named < 1.0


@pytest.mark.contract
@pytest.mark.parametrize("question", ["火 摘要", "overview", "摘要"])
def test_a_question_with_nothing_to_compare_keeps_the_page(question: str) -> None:
    atlas = PAGES[1]
    store: Any = _Store(atlas)

    assert wiki_page_relevance(question, atlas, PAGES) is None
    candidates, steps = collect_wiki_candidates(question, wiki_store=store, is_primary=True)

    assert [candidate.score for candidate in candidates] == [1.0]
    assert steps[0].detail["hit"] is True and "relevance" not in steps[0].detail


@pytest.mark.contract
def test_a_page_that_shares_only_its_subject_is_still_offered() -> None:
    owner = _page("atlas", "Atlas", "Owner: Alice.")
    store: Any = _Store(owner)
    store.list_pages = lambda: [owner]

    candidates, steps = collect_wiki_candidates(
        "Who owns Atlas?", wiki_store=store, is_primary=True
    )

    assert len(candidates) == 1 and 0.7 <= candidates[0].score < 1.0
    assert 0.0 < steps[0].detail["relevance"] < 0.15


class _Store:
    def __init__(self, found: WikiPage) -> None:
        self.found = found

    def search(self, question: str, *, pages: list[WikiPage] | None = None) -> WikiPage:
        return self.found

    def list_pages(self) -> list[WikiPage]:
        return PAGES

    def overview(self) -> str:
        return ""


@pytest.mark.contract
@pytest.mark.parametrize(("is_primary", "base"), [(True, 1.0), (False, 0.65)])
def test_wiki_score_follows_relevance(is_primary: bool, base: float) -> None:
    atlas = PAGES[1]
    store: Any = _Store(atlas)

    exact, steps = collect_wiki_candidates("Project Atlas", wiki_store=store, is_primary=is_primary)
    partial, _ = collect_wiki_candidates(
        "Project Atlas 的負責人是誰", wiki_store=store, is_primary=is_primary
    )

    assert exact[0].score == pytest.approx(base)
    assert base * 0.7 < partial[0].score < base
    assert steps[0].detail["hit"] is True and steps[0].detail["relevance"] == 1.0


@pytest.mark.contract
def test_a_page_found_by_accident_is_not_a_candidate() -> None:
    store: Any = _Store(PAGES[0])

    candidates, steps = collect_wiki_candidates(
        "agent security and capability testing framework 做了什麼",
        wiki_store=store,
        is_primary=True,
    )

    assert candidates == []
    assert steps[0].kind == "wiki_lookup"
    assert steps[0].detail == {
        "hit": False,
        "reason": "low-relevance",
        "slug": "memory-candidate",
        "relevance": 0.0,
    }


@pytest.mark.contract
def test_a_substring_match_no_longer_answers_with_an_unrelated_page(
    cli_runner, tmp_path: Path
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name, text in DOCS.items():
        (docs / name).write_text(text, encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0

    # "candid" is inside "Candidate": the page search finds the empty page.
    result = cli_runner.invoke(app, ["query", "candid 摘要", "--writeback=no"])
    payload = validate(json.loads(result.stdout))

    lookup = [s["detail"] for s in payload["trace"]["steps"] if s["kind"] == "wiki_lookup"]
    assert lookup == [
        {"hit": False, "reason": "low-relevance", "slug": "memory-candidate", "relevance": 0.0}
    ]
    assert payload["source"] != ["wiki"]
    assert "No candidates" not in payload["answer"]
