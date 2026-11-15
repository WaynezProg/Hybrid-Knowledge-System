"""030：只與問句共用疑問詞的 wiki 頁面不成為候選。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.core.schema import validate
from hks.retrievers.wiki import collect_wiki_candidates, shares_subject, subject_terms
from hks.storage.wiki import WikiPage


def _page(slug: str, title: str, body: str, *, origin: str = "writeback") -> WikiPage:
    return WikiPage(
        slug=slug,
        title=title,
        summary=body,
        body=body,
        source_relpath=f"{slug}.md",
        origin=origin,  # type: ignore[arg-type]
        updated_at="2026-11-15T00:00:00+00:00",
    )


BOLT_EN = _page(
    "what-risk-does-the-bolt-cache-have",
    "What risk does the Bolt cache have",
    "Bolt Cache The Bolt cache layer has a known eviction risk under memory pressure.",
)
BOLT_ZH = _page("bolt-cache-zh", "Bolt 快取做了什麼", "Bolt 快取層新增了淘汰策略。")


class _Store:
    def __init__(self, found: WikiPage, *others: WikiPage) -> None:
        self.found = found
        self.pages = [found, *others]

    def search(self, question: str, *, pages: list[WikiPage] | None = None) -> WikiPage:
        return self.found

    def list_pages(self) -> list[WikiPage]:
        return self.pages

    def overview(self) -> str:
        return ""


@pytest.mark.contract
def test_question_words_are_not_subject_terms() -> None:
    assert subject_terms("When is the Atlas migration scheduled") == {
        "atlas",
        "migration",
        "scheduled",
    }
    assert subject_terms("Atlas 遷移做了什麼？") == {"atlas", "遷移"}
    assert subject_terms("為什麼 Atlas 延遲") == {"atlas", "延遲"}
    # A word written in capitals is a name.
    assert "it" in subject_terms("Who runs IT")
    assert "it" not in subject_terms("Who runs it")
    # Words that ask for a kind of answer stay (024, decision 2).
    assert subject_terms("summary Atlas") == {"summary", "atlas"}


@pytest.mark.contract
@pytest.mark.parametrize(
    ("question", "page"),
    [
        ("When is the Atlas migration scheduled", BOLT_EN),
        ("Atlas 遷移做了什麼", BOLT_ZH),
    ],
)
def test_a_page_sharing_only_question_words_is_not_a_candidate(
    question: str, page: WikiPage
) -> None:
    store: Any = _Store(page, _page("ops", "Ops status", "checkout latency is stable."))

    candidates, steps = collect_wiki_candidates(question, wiki_store=store, is_primary=True)

    assert not shares_subject(question, page)
    assert candidates == []
    detail = steps[0].detail
    assert detail["hit"] is False and detail["reason"] == "low-relevance"
    assert detail["slug"] == page.slug and detail["relevance"] > 0.0


@pytest.mark.contract
@pytest.mark.parametrize(
    ("question", "page"),
    [
        ("What risk does the Bolt cache have", BOLT_EN),
        ("Does Bolt evict under pressure", BOLT_EN),
        ("Bolt 快取做了什麼", BOLT_ZH),
        ("Who owns Atlas?", _page("atlas", "Atlas", "Owner: Alice.", origin="ingest")),
    ],
)
def test_a_page_sharing_a_subject_term_is_still_offered(question: str, page: WikiPage) -> None:
    store: Any = _Store(page)

    candidates, steps = collect_wiki_candidates(question, wiki_store=store, is_primary=True)

    assert len(candidates) == 1 and steps[0].detail["hit"] is True


@pytest.mark.contract
@pytest.mark.parametrize("question", ["what is it", "做了什麼", "為什麼？"])
def test_a_question_of_only_question_words_keeps_the_page(question: str) -> None:
    assert subject_terms(question) == set()
    assert shares_subject(question, BOLT_EN)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("asked", "approved"),
    [
        ("When is the Atlas migration scheduled", "What risk does the Bolt cache have"),
        ("Atlas 遷移做了什麼", "Bolt 快取做了什麼"),
    ],
)
def test_a_writeback_page_does_not_answer_a_question_about_something_else(
    cli_runner, tmp_path: Path, asked: str, approved: str
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "atlas.md").write_text(
        "# Atlas Migration\n\nThe Atlas database migration is scheduled for March 14. "
        "Atlas 遷移排定在三月十四日。\n",
        encoding="utf-8",
    )
    (docs / "bolt.md").write_text(
        "# Bolt Cache\n\nThe Bolt cache layer has a known eviction risk under memory "
        "pressure. Bolt 快取層有淘汰風險。\n",
        encoding="utf-8",
    )
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    enqueued = json.loads(cli_runner.invoke(app, ["query", approved, "--writeback=yes"]).stdout)
    item_id = next(
        s["detail"]["id"] for s in enqueued["trace"]["steps"] if s["kind"] == "writeback"
    )
    assert cli_runner.invoke(app, ["writeback", "approve", item_id]).exit_code == 0
    (docs / "atlas.md").unlink()
    assert cli_runner.invoke(app, ["ingest", str(docs), "--prune"]).exit_code == 0

    payload = validate(json.loads(cli_runner.invoke(app, ["query", asked]).stdout))

    lookup = [s["detail"] for s in payload["trace"]["steps"] if s["kind"] == "wiki_lookup"]
    assert all(not step["hit"] for step in lookup)
    assert payload["source"] != ["wiki"]
    assert "Bolt" not in payload["answer"]
