"""Unit tests for query writeback queue item construction."""

from __future__ import annotations

import pytest

from hks.commands.query import _build_queue_item
from hks.core.schema import QueryResponse, Trace
from hks.retrieval.confidence import ConfidenceAssessment


def _make_response() -> QueryResponse:
    return QueryResponse(
        answer="test answer",
        source=["wiki"],
        confidence=0.9,
        trace=Trace(route="wiki", steps=[]),
        evidence=[
            {"source_relpath": "atlas.txt", "route": "wiki", "quote": "atlas"},
        ],
        retrieval_score=0.9,
        writeback_eligible=False,
    )


@pytest.mark.unit
def test_build_queue_item_copies_query_response_fields() -> None:
    assessment = ConfidenceAssessment(
        retrieval_score=0.9,
        confidence=0.9,
        writeback_eligible=False,
        reasons=["wiki route: auto writeback ineligible (use --writeback=yes)"],
    )

    item = _build_queue_item(
        question="summary Atlas",
        response=_make_response(),
        assessment=assessment,
    )

    assert item.question == "summary Atlas"
    assert item.answer == "test answer"
    assert item.route == "wiki"
    assert item.source == ["wiki"]
    assert item.evidence == [{"quote": "atlas", "route": "wiki", "source_relpath": "atlas.txt"}]
    assert item.retrieval_score == 0.9
    assert item.writeback_eligible is False
    assert item.reasons == ["wiki route: auto writeback ineligible (use --writeback=yes)"]


@pytest.mark.unit
def test_build_queue_item_uses_response_values_when_assessment_missing() -> None:
    item = _build_queue_item(
        question="summary Atlas",
        response=_make_response(),
        assessment=None,
    )

    assert item.retrieval_score == 0.9
    assert item.writeback_eligible is False
    assert item.reasons == []
