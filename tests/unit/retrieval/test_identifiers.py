"""Identifier terms: what a question names specifically, and whether content holds it."""

from __future__ import annotations

import pytest

from hks.retrieval.bm25 import holds_identifiers, identifier_terms


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("ERR-4012 怎麼修", {"4012"}),
        ("INC-00001", {"00001"}),
        ("build 7.14.3-rc2 status", {"rc2"}),
        ("who owns svc01", {"svc01"}),
        ("migrate_0417_drop_legacy.sql", {"0417"}),
        ("top 10 risks", set()),
        ("2026 roadmap", set()),
        ("2026-05-21 做了什麼", set()),
        ("clause 3.2 text", set()),
        ("Atlas 有哪些主要風險", set()),
    ],
)
def test_identifier_terms(question: str, expected: set[str]) -> None:
    assert identifier_terms(question) == expected


def test_holds_identifiers_needs_every_one_as_a_whole_term() -> None:
    assert holds_identifiers(set(), "anything")
    assert holds_identifiers({"4012"}, "Ticket ERR-4012 was resolved")
    assert not holds_identifiers({"4012"}, "Ticket ERR-40129 was resolved"), "not a prefix"
    assert not holds_identifiers({"4012", "rc2"}, "ERR-4012 only")
