"""Identifier terms: what a question names specifically, and whether content holds it."""

from __future__ import annotations

import pytest

from hks.retrieval.bm25 import (
    bm25_rank,
    holds_identifiers,
    identifier_terms,
    query_coverage,
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # letters followed by a number: one spelling, whatever joins them
        ("ERR-4012 怎麼修", {"err-4012"}),
        ("INC-00001", {"inc-00001"}),
        ("VID236 的畫面", {"vid-236"}),
        ("VID_236 的畫面", {"vid-236"}),
        ("who owns svc01", {"svc-01"}),
        ("build 7.14.3-rc2 status", {"rc-2"}),
        ("What is CVE-2031-7781 about?", {"cve-2031-7781"}),
        ("migrate_0417_drop_legacy.sql", {"migrate-0417"}),
        # the letters make a short number specific
        ("Atlas-10 對應哪一個 risk", {"atlas-10"}),
        # other codes that mix letters and digits
        ("v17r2-audio", {"v17r2"}),
        ("commit 8c5487a", {"8c5487a"}),
        # a number on its own
        ("Budget 135 的 ETA", {"135"}),
        # a name with a digit inside it is a word, not a code
        ("session2memory reconcile 步驟", set()),
        ("k8s 與 i18n 的 e2e 測試", set()),
        # topics
        ("top 10 risks", set()),
        ("2026 roadmap", set()),
        ("2026-05-21 做了什麼", set()),
        ("clause 3.2 text", set()),
        ("Atlas 有哪些主要風險", set()),
        ("who owns svc-ledger-sync", set()),
    ],
)
def test_identifier_terms(question: str, expected: set[str]) -> None:
    assert identifier_terms(question) == expected


def test_holds_identifiers_needs_every_one_as_a_whole_term() -> None:
    assert holds_identifiers(set(), "anything")
    assert holds_identifiers({"4012"}, "Ticket ERR-4012 was resolved")
    assert not holds_identifiers({"4012"}, "Ticket ERR-40129 was resolved"), "not a prefix"
    assert not holds_identifiers({"4012", "rc-2"}, "ERR-4012 only")
    assert holds_identifiers({"135", "v17r2"}, "v17r2 costs 135")


@pytest.mark.parametrize(
    ("content", "held"),
    [
        ("依 VID-236 畫面選", True),
        ("vid236 的畫面", True),
        ("VID_236", True),
        ("VID 236", True),
        ("VID  236", True),
        ("VID\t236", True),
        ("VID\u00a0236", True),
        ("VID\n236", False),
        ("VID-236-2 是補拍", True),
        ("VID-2361", False),
        ("VID-23", False),
        ("XVID-236", False),
        ("VID 專案共 236 支", False),
        ("只提到 236", False),
    ],
)
def test_a_compound_code_is_found_in_any_spelling_but_not_in_another_code(
    content: str, held: bool
) -> None:
    assert holds_identifiers({"vid-236"}, content) is held


def test_a_short_numbered_code_is_not_held_by_the_bare_words() -> None:
    assert holds_identifiers({"atlas-10"}, "| 10 | Atlas-10 | risk-10 |")
    assert not holds_identifiers({"atlas-10"}, "Atlas 專案目前有 10 個主要風險")
    assert not holds_identifiers({"atlas-10"}, "Atlas-1 與 Atlas-100")


CORPUS = [
    "依 VID-236 畫面選第三段的 A 版或 B 版",
    "VID-2361 是另一支影片的編號",
    "Ticket ERR-4012 was resolved by rotating the gateway token",
    "每週例會沒有特別事項",
]


@pytest.mark.parametrize("spelling", ["VID-236", "VID236", "vid_236"])
def test_keyword_ranking_finds_a_code_in_either_spelling(spelling: str) -> None:
    ranked = bm25_rank(spelling, CORPUS, top_k=3)

    assert ranked and ranked[0][0] == 0
    assert query_coverage(spelling, CORPUS[0], CORPUS) == pytest.approx(1.0)


def test_a_joined_code_is_also_found_where_the_content_joins_it() -> None:
    corpus = [*CORPUS, "svc01 由 Priya 負責"]

    assert bm25_rank("svc-01", corpus, top_k=1)[0][0] == len(corpus) - 1


def test_an_unknown_code_is_not_covered_by_a_code_sharing_its_letters() -> None:
    known = query_coverage("ERR-4012", CORPUS[2], CORPUS)
    for unknown in ("ERR-9999", "ERR9999"):
        assert query_coverage(unknown, CORPUS[2], CORPUS) < 0.5 < known


def test_a_joined_code_is_fully_covered_by_content_that_joins_it() -> None:
    assert query_coverage("svc01", "svc01", ["svc01"]) == pytest.approx(1.0)
    assert query_coverage("svc-01", "svc01 owner", ["svc01 owner", "x y"]) > 0.5


def test_the_pieces_of_a_code_apart_do_not_cover_it() -> None:
    apart = "ERR-4012 handles 9999 requests"

    assert query_coverage("ERR9999", apart, [apart]) == 0.0
    assert query_coverage("Lot7", "lot inventory", ["lot inventory"]) == 0.0


def test_content_with_the_pieces_apart_does_not_crowd_out_the_code() -> None:
    documents = ["VID236 " + "notes " * 100, *["VID status 236"] * 5]

    unfiltered = bm25_rank("VID236", documents, top_k=5)
    filtered = bm25_rank("VID236", documents, top_k=5, required=identifier_terms("VID236"))

    assert 0 not in [index for index, _ in unfiltered], "the long document ranks below the five"
    assert [index for index, _ in filtered] == [0]
