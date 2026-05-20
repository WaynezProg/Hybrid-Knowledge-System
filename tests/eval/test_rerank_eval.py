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
    from hks.commands.query import Candidate, _llm_rerank

    candidates = [
        Candidate(
            text=c["text"],
            source_route=c["route"],
            score=c["score"],
            metadata={},
        )
        for c in case["candidates"]
    ]

    ranked = _llm_rerank(case["question"], candidates)

    assert ranked[0].source_route == case["expected_top_route"], (
        f"Expected top route {case['expected_top_route']}, got {ranked[0].source_route}"
    )
