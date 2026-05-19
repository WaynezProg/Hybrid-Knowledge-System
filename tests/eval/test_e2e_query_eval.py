"""Eval runner for end-to-end query pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval.conftest import requires_openai

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "e2e_query.jsonl"


def _load_cases() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    return [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


@requires_openai
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_e2e_query_eval(case: dict, tmp_path: Path) -> None:
    pytest.skip("E2E eval requires a fully ingested KS root — run manually with a prepared fixture")
