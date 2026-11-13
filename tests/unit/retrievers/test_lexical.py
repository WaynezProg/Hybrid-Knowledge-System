"""Unit tests for the opt-in lexical route."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hks.retrieval.bm25 import query_coverage
from hks.retrieval.confidence import assess
from hks.retrieval.evidence import candidate_evidence
from hks.retrievers.lexical import collect_lexical_candidates
from hks.retrievers.vector import hybrid_search_mode
from hks.storage.vector import SearchHit


def _store(texts: list[str]) -> MagicMock:
    vector_store = MagicMock()
    vector_store.count.return_value = len(texts)
    vector_store.all_chunks.return_value = [
        SearchHit(
            chunk_id=f"c{index}",
            text=text,
            similarity=0.0,
            metadata={"source_relpath": f"{index}.md"},
        )
        for index, text in enumerate(texts)
    ]
    vector_store.paths = MagicMock()
    return vector_store


def _manifest() -> MagicMock:
    manifest = MagicMock()
    manifest.entries = {}
    return manifest


TEXTS = [
    "general remarks about planning",
    "ticket ERR-4012 is fixed by rotating the token",
    "more general remarks about planning",
]


def test_mode_names(monkeypatch: pytest.MonkeyPatch) -> None:
    modes = (("", "route"), ("route", "route"), ("fused", "fused"), ("1", "fused"), ("0", "off"))
    for value, mode in modes:
        monkeypatch.setenv("HKS_HYBRID_SEARCH", value)
        assert hybrid_search_mode() == mode


def test_route_is_silent_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "fused")
    store = _store(TEXTS)
    assert collect_lexical_candidates("ERR-4012", vector_store=store, manifest=_manifest()) == (
        [],
        [],
    )
    store.all_chunks.assert_not_called()


def test_route_returns_keyword_matches_scored_by_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "route")
    candidates, steps = collect_lexical_candidates(
        "ERR-4012", vector_store=_store(TEXTS), manifest=_manifest()
    )

    assert [c.metadata["source_relpath"] for c in candidates] == ["1.md"]
    assert candidates[0].source_route == "lexical"
    assert candidates[0].score == 0.85, "every term of the question is in the chunk"
    assert steps[0].kind == "lexical_lookup" and steps[0].detail["hit"] is True
    assert candidate_evidence(candidates[0])[0]["route"] == "lexical"

    none, steps = collect_lexical_candidates(
        "nothing matches", vector_store=_store(TEXTS), manifest=_manifest()
    )
    assert none == [] and steps[0].detail["hit"] is False


def test_route_skips_a_store_above_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "route")
    monkeypatch.setenv("HKS_HYBRID_MAX_CHUNKS", "1")
    store = _store(TEXTS)
    candidates, steps = collect_lexical_candidates(
        "ERR-4012", vector_store=store, manifest=_manifest()
    )
    assert candidates == [] and steps[0].detail["lexical_skipped"] == "chunk_count_above_limit"
    store.all_chunks.assert_not_called()


def test_coverage_weights_rare_terms_more() -> None:
    assert query_coverage("ERR-4012", TEXTS[1], TEXTS) == 1.0
    assert query_coverage("ERR-4012", TEXTS[0], TEXTS) == 0.0
    partial = query_coverage("planning ERR-4012", TEXTS[0], TEXTS)
    assert 0.0 < partial < 0.5, "the common word alone is worth less than half"
    assert query_coverage("", TEXTS[0], TEXTS) == 0.0


def test_lexical_answers_are_never_written_back_on_their_own() -> None:
    evidence = [{"source_relpath": "1.md", "route": "lexical", "quote": "ticket ERR-4012"}]
    high = assess(route="lexical", raw_score=0.85, evidence=evidence)
    assert not high.writeback_eligible and high.calibrated_confidence == 0.85
    assert "lexical" in high.reasons[0]


def test_a_chunk_the_vector_route_nominated_stays_with_the_vector_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hks.retrieval.models import Candidate

    monkeypatch.setenv("HKS_HYBRID_SEARCH", "route")
    texts = [*TEXTS, "ERR-4012 also appears in this second note"]
    nominated = Candidate(
        text=texts[1],
        source_route="vector",
        score=0.5,
        metadata={"chunk_id": "c1", "source_relpath": "1.md"},
    )

    candidates, steps = collect_lexical_candidates(
        "ERR-4012",
        vector_store=_store(texts),
        manifest=_manifest(),
        vector_candidates=[nominated],
    )

    assert [c.metadata["chunk_id"] for c in candidates] == ["c3"], "only what vector missed"
    assert nominated.source_route == "vector" and nominated.score == 0.5
    assert nominated.metadata["lexical_rank"] in (1, 2) and "bm25_score" in nominated.metadata
    assert steps[0].detail["shared_with_vector"] == 1


def test_a_chunk_without_the_identifier_asked_about_is_not_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_HYBRID_SEARCH", "route")
    texts = [*TEXTS, "incident INC-90217 was caused by an expired certificate"]

    wrong, steps = collect_lexical_candidates(
        "INC-00001", vector_store=_store(texts), manifest=_manifest()
    )
    right, _ = collect_lexical_candidates(
        "INC-90217 怎麼修", vector_store=_store(texts), manifest=_manifest()
    )

    assert wrong == [] and steps[0].detail["skipped_missing_identifier"] == 1
    assert [c.metadata["source_relpath"] for c in right] == ["3.md"]
