"""Unit tests for LLM reranker fallback behavior."""

from __future__ import annotations

import pytest

from hks.rerank.llm import classify_rerank_error, llm_rerank, rerank_candidates
from hks.retrieval.models import Candidate


def test_rerank_candidates_uses_rrf_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    candidates = [
        Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
        Candidate(text="b", source_route="vector", score=0.5, metadata={}),
    ]

    ranked, strategy, detail = rerank_candidates("question", candidates)

    assert strategy == "rrf"
    assert detail["strategy"] == "rrf"
    assert ranked[0].text == "a"


def test_uses_rrf_when_api_key_set_without_network_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("HKS_LLM_NETWORK_OPT_IN", raising=False)

    def fail_llm_rerank(*_args: object, **_kwargs: object) -> tuple[
        list[Candidate], dict[str, object]
    ]:
        raise AssertionError("LLM rerank must require HKS_LLM_NETWORK_OPT_IN=1")

    monkeypatch.setattr("hks.rerank.llm.llm_rerank", fail_llm_rerank)

    candidates = [
        Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
        Candidate(text="b", source_route="vector", score=0.5, metadata={}),
    ]

    ranked, strategy, detail = rerank_candidates("question", candidates)

    assert strategy == "rrf"
    assert detail["strategy"] == "rrf"
    assert [candidate.text for candidate in ranked] == ["a", "b"]


def test_llm_fallback_captures_timeout_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "1")
    monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")

    def mock_openai_chat(**_kwargs: object) -> object:
        raise TimeoutError("mock timeout")

    monkeypatch.setattr("hks.rerank.llm._openai_chat", mock_openai_chat)

    candidates = [Candidate(text="a", source_route="wiki", score=1.0, metadata={})]
    ranked, detail = llm_rerank("q", candidates)

    assert ranked[0].text == "a"
    assert detail["strategy"] == "llm"
    assert detail["status"] == "fallback"
    assert detail["fallback_strategy"] == "rrf"
    assert detail["reason"] == "openai_timeout"


def test_classify_rerank_error_maps_value_error_to_invalid_ranking() -> None:
    assert classify_rerank_error(ValueError("bad")) == "openai_invalid_ranking"
