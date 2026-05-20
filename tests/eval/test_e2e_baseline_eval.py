"""Baseline E2E eval that works without OpenAI (RRF fallback only).

Validates the fused-retrieval pipeline core: ingest fixtures, query
through wiki + graph + vector → RRF rerank → merge.  No LLM reranker
needed — RRF is the core ranking ability and must always work.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.commands.query import run as query_run
from hks.core.manifest import load_manifest
from hks.core.paths import runtime_paths
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "e2e_baseline.jsonl"
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


def _force_rrf_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make this baseline eval deterministic even on machines with OpenAI configured."""
    monkeypatch.setenv("HKS_CONFIG_FILE", str(tmp_path / "missing.yaml"))
    monkeypatch.setenv("HKS_CONFIG_ENV", str(tmp_path / "missing.env"))
    monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "0")
    monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _install_enriched_page_tree_summary(ks_root: Path) -> None:
    """Add one LLM-enriched section summary so E2E covers a real page_tree hit."""
    paths = runtime_paths(ks_root)
    manifest = load_manifest(paths.manifest)
    relpath = "project-atlas.txt"
    entry = manifest.entries[relpath]
    assert entry.derived.page_tree is not None

    tree = PageTree(
        source_relpath=relpath,
        source_format=entry.format,
        doc_title="Project Atlas",
        root_nodes=[
            TreeNode(
                node_id="pt-enriched-summary",
                title="Nebula Arbitration",
                level=1,
                start_offset=0,
                end_offset=entry.size_bytes,
                children=[],
                summary=(
                    "Nebula arbitration requires coordinator approval before "
                    "the midnight cutover."
                ),
                metadata={"page_start": 12, "page_end": 14},
            )
        ],
        build_method="test-enriched",
        built_at=entry.ingested_at,
        total_nodes=1,
        source_sha256=entry.sha256,
    )
    TreeStore(paths).save(relpath, tree)


@pytest.fixture()
def ingested_ks_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ingest fixture docs into the KS root prepared by ``_test_env``."""
    _force_rrf_only(monkeypatch, tmp_path)
    docs_dir = tmp_path / "docs"
    _copy_fixture_files(docs_dir)

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(docs_dir)])
    assert result.exit_code == 0, f"Ingest failed:\n{result.stdout}"
    ks_root = tmp_path / "ks"
    _install_enriched_page_tree_summary(ks_root)
    return ks_root


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
def test_e2e_baseline_rrf(case: dict, ingested_ks_root: Path) -> None:
    """Core pipeline correctness without any LLM dependency."""
    question: str = case["question"]

    response = query_run(question, writeback="no")
    payload = response.to_dict()

    # 1. Pipeline must return a real answer.
    if case.get("expected_answer_not_fallback", False):
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

    # 3. RRF fallback must have been used (no OpenAI key in test env).
    assert merge_detail["strategy"] == "rrf", (
        f"Expected rrf strategy, got {merge_detail['strategy']} for: {question}"
    )

    # 4. Optional winning-source check.
    expected_source: str | None = case.get("expected_source")
    if expected_source is not None:
        assert payload["source"] == [expected_source], (
            f"Expected source {expected_source} for: {question}, "
            f"got: {payload['source']}"
        )
        assert payload["trace"]["route"] == expected_source

    # 5. Evidence should be present for any confident response.
    if payload["confidence"] > 0:
        assert payload.get("evidence"), f"Missing evidence for: {question}"

    # 6. Optional keyword check on the answer.
    expected_contains: str | None = case.get("expected_answer_contains")
    if expected_contains is not None:
        assert expected_contains.lower() in payload["answer"].lower(), (
            f"Expected '{expected_contains}' in answer for: {question}, "
            f"got: {payload['answer'][:200]}"
        )

    # 7. page_tree_lookup step must exist (collector was wired in).
    pt_steps = [s for s in steps if s["kind"] == "page_tree_lookup"]
    assert pt_steps, (
        f"No page_tree_lookup step in trace for: {question} — "
        "collector may not be wired into the pipeline"
    )
    expected_page_tree_hit: bool | None = case.get("expected_page_tree_hit")
    if expected_page_tree_hit is not None:
        detail = pt_steps[0]["detail"]
        assert detail["hit"] is expected_page_tree_hit
        if expected_page_tree_hit:
            assert detail["candidate_count"] > 0
