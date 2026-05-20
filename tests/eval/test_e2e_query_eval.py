"""Eval runner for end-to-end query pipeline.

Ingests the standard fixture documents into a fresh KS root,
then runs each eval case through the full fused-retrieval pipeline
(wiki + graph + vector → LLM rerank → merge) and validates:

  1. The pipeline produces a non-fallback answer.
  2. A ``merge`` trace step exists (fused retrieval ran).
  3. Expected source collectors produced at least one candidate.
  4. Evidence is attached to the response.
  5. Optional keyword check on the answer text.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.commands.query import run as query_run

from .conftest import requires_openai

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "e2e_query.jsonl"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "valid"


def _load_cases() -> list[dict]:
    if not EVAL_PATH.exists():
        return []
    return [json.loads(line) for line in EVAL_PATH.read_text().splitlines() if line.strip()]


def _copy_fixture_files(target: Path) -> None:
    """Copy plain-text fixture files (skip subdirectories like docx/)."""
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(FIXTURES_DIR.iterdir()):
        if child.is_file():
            shutil.copy2(child, target / child.name)


def _trace_source_routes(steps: list[dict]) -> set[str]:
    """Extract which source routes produced at least one hit from trace steps."""
    routes: set[str] = set()
    for step in steps:
        kind = step["kind"]
        detail = step.get("detail", {})
        if kind == "wiki_lookup" and detail.get("hit"):
            routes.add("wiki")
        elif kind == "graph_lookup" and detail.get("hit"):
            routes.add("graph")
        elif kind == "vector_lookup" and detail.get("top_similarity", 0) > 0:
            routes.add("vector")
    return routes


@pytest.fixture()
def ingested_ks_root(tmp_path: Path) -> Path:
    """Ingest fixture docs into the KS root prepared by ``_test_env``."""
    docs_dir = tmp_path / "docs"
    _copy_fixture_files(docs_dir)

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(docs_dir)])
    assert result.exit_code == 0, f"Ingest failed:\n{result.stdout}"
    return tmp_path / "ks"


@requires_openai
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_e2e_query_eval(case: dict, ingested_ks_root: Path) -> None:
    question: str = case["question"]

    response = query_run(question, writeback="no")
    payload = response.to_dict()

    # 1. Pipeline must return a real answer (not the no-hit fallback).
    assert payload["answer"] != "未能於現有知識中找到答案", (
        f"Got no-hit fallback for: {question}"
    )

    # 2. Fused retrieval must produce a merge step.
    steps = payload["trace"]["steps"]
    merge_steps = [s for s in steps if s["kind"] == "merge"]
    assert merge_steps, f"No merge step in trace for: {question}"

    merge_detail = merge_steps[0]["detail"]
    assert merge_detail["candidate_count"] > 0, (
        f"Merge step has 0 candidates for: {question}"
    )

    # 3. Expected source collectors produced candidates.
    active_routes = _trace_source_routes(steps)
    expected_sources: list[str] = case.get("expected_sources_present", [])
    for source in expected_sources:
        assert source in active_routes, (
            f"Expected {source} to produce a hit for: {question} "
            f"(active routes: {active_routes})"
        )

    # 4. Evidence should be present for any confident response.
    if payload["confidence"] > 0:
        assert payload.get("evidence"), f"Missing evidence for: {question}"

    # 5. Optional keyword check on the answer.
    expected_contains: str | None = case.get("expected_answer_contains")
    if expected_contains is not None:
        assert expected_contains.lower() in payload["answer"].lower(), (
            f"Expected '{expected_contains}' in answer for: {question}, "
            f"got: {payload['answer'][:200]}"
        )
