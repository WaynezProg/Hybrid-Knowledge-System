"""Eval runner for LLM reranker quality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import requires_openai

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "rerank.jsonl"


def _load_cases() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    return [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


@requires_openai
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_rerank_eval(case: dict) -> None:
    from hks.rerank.llm import llm_rerank
    from hks.retrieval.models import Candidate

    candidates = [
        Candidate(
            text=c["text"],
            source_route=c["route"],
            score=c["score"],
            metadata={},
        )
        for c in case["candidates"]
    ]

    ranked, detail = llm_rerank(case["question"], candidates)

    assert detail["strategy"] in {"llm", "rrf"}
    assert ranked[0].source_route == case["expected_top_route"], (
        f"Expected top route {case['expected_top_route']}, got {ranked[0].source_route}"
    )


def test_rerank_eval_fallback_path_preserves_candidate_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hks.rerank.llm import llm_rerank
    from hks.retrieval.models import Candidate

    monkeypatch.setattr("hks.rerank.llm.hosted_provider_ready", lambda _provider: False)
    candidates = [
        Candidate(text=f"candidate-{index}", source_route="wiki", score=1.0, metadata={})
        for index in range(12)
    ]

    ranked, detail = llm_rerank("q", candidates)

    assert detail["status"] == "fallback"
    assert detail["fallback_strategy"] == "rrf"
    assert len(ranked) == len(candidates)


def test_rerank_eval_success_path_preserves_uncapped_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hks.rerank.llm import llm_rerank
    from hks.retrieval.models import Candidate

    monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "1")
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")

    def mock_openai_chat(**_kwargs: object) -> object:
        return {"ranking": [1, 0]}

    monkeypatch.setattr("hks.rerank.llm._openai_chat", mock_openai_chat)
    candidates = [
        Candidate(text=f"candidate-{index}", source_route="wiki", score=1.0, metadata={})
        for index in range(12)
    ]

    ranked, detail = llm_rerank("q", candidates)

    assert detail["status"] == "success"
    assert [candidate.text for candidate in ranked[-2:]] == ["candidate-10", "candidate-11"]
    assert len(ranked) == len(candidates)
