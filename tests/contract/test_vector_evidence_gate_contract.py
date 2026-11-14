"""026：vector 答案既沒有足夠的相似度、內容也幾乎不含問句的詞時，回 no-hit。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.commands import query as query_module
from hks.core.schema import validate
from hks.retrieval.models import Candidate

DOCS = {
    "ledger.md": "# Ledger\n\nThe monthly ledger close moved to the third working day.\n",
    "search.md": "# Search\n\nIndex rebuilds on the catalog cluster take about two hours.\n",
    "mobile.md": "# Mobile\n\nCrash triage for the handheld client happens every Tuesday.\n",
    "storage.md": "# Storage\n\nCold archive retrieval usually takes twelve hours.\n",
}


@pytest.fixture()
def ask(cli_runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Queries a small knowledge base; ``similarity`` stands in for what an embedding
    model would report for the nearest chunk, so the case does not depend on a model."""
    docs = tmp_path / "docs"
    docs.mkdir()
    for name, text in DOCS.items():
        (docs / name).write_text(text, encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    real = query_module.collect_vector_candidates
    wanted: dict[str, float] = {}

    def with_similarity(question: str, **arguments: Any):  # type: ignore[no-untyped-def]
        candidates, steps = real(question, **arguments)
        for index, candidate in enumerate(candidates):
            similarity = wanted["similarity"] - index * 0.01
            candidate.metadata["vector_similarity"] = similarity
            candidate.metadata["lexical_overlap"] = 0
            candidate.metadata["final_score"] = similarity
            candidates[index] = Candidate(
                text=candidate.text,
                source_route="vector",
                score=similarity,
                metadata=candidate.metadata,
            )
        return candidates, steps

    monkeypatch.setattr(query_module, "collect_vector_candidates", with_similarity)

    def run(question: str, *, similarity: float) -> dict[str, Any]:
        wanted["similarity"] = similarity
        result = cli_runner.invoke(app, ["query", question, "--writeback=no"])
        assert result.exit_code == 0, result.stdout
        return validate(json.loads(result.stdout))

    return run


def _fallback(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [step["detail"] for step in payload["trace"]["steps"] if step["kind"] == "fallback"]


@pytest.mark.contract
def test_the_nearest_chunk_of_an_unrelated_question_is_not_an_answer(ask) -> None:
    payload = ask("量子電腦採購計畫", similarity=0.27)

    assert payload["source"] == [] and payload["confidence"] == 0.0
    [fallback] = _fallback(payload)
    assert fallback["status"] == "no-hit" and fallback["reason"] == "weak_evidence"
    assert fallback["route"] == "vector"
    assert fallback["vector_similarity"] == 0.27 and fallback["query_coverage"] == 0.0
    assert fallback["thresholds"] == {"vector_similarity": 0.3, "query_coverage": 0.05}


@pytest.mark.contract
def test_a_sure_embedding_answers_without_shared_words(ask) -> None:
    """A paraphrase shares no word with its answer; the similarity is what speaks for it."""
    payload = ask("量子電腦採購計畫", similarity=0.36)

    assert payload["source"] == ["vector"] and _fallback(payload) == []


@pytest.mark.contract
def test_shared_rare_words_answer_at_a_low_similarity(ask) -> None:
    payload = ask("ledger close", similarity=0.27)

    assert payload["source"] != [] and _fallback(payload) == []
    assert {item["source_relpath"] for item in payload["evidence"]} == {"ledger.md"}


@pytest.mark.contract
def test_an_answer_refused_by_the_score_gate_keeps_that_reason(ask) -> None:
    payload = ask("量子電腦採購計畫", similarity=0.1)

    [fallback] = _fallback(payload)
    assert fallback["reason"] == "final_score_below_threshold"


def test_without_a_measured_coverage_nothing_is_taken_away() -> None:
    """Keyword retrieval off or skipped: the candidate carries no coverage."""
    unmeasured = Candidate(
        text="x", source_route="vector", score=0.27, metadata={"vector_similarity": 0.27}
    )
    measured = Candidate(
        text="x",
        source_route="vector",
        score=0.27,
        metadata={"vector_similarity": 0.27, "query_coverage": 0.0},
    )
    wiki = Candidate(text="x", source_route="wiki", score=0.27, metadata=dict(measured.metadata))

    assert query_module._weak_evidence(unmeasured) is None
    assert query_module._weak_evidence(wiki) is None
    assert query_module._weak_evidence(measured) == {
        "vector_similarity": 0.27,
        "query_coverage": 0.0,
    }
