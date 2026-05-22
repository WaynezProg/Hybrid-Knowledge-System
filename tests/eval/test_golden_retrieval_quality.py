"""Deterministic golden retrieval quality gate for CI."""

from __future__ import annotations

import hashlib
import math
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hks.cli import app
from hks.commands.query import run as query_run
from hks.core.manifest import load_manifest
from hks.core.paths import runtime_paths
from hks.evaluation.retrieval_quality import (
    MetricThresholds,
    QueryObservation,
    assert_thresholds,
    compute_metrics,
    load_golden_cases,
)
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore

EVAL_PATH = Path(__file__).resolve().parents[2] / "evals" / "golden_queries" / "quick.jsonl"
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "valid"


def _copy_fixture_files(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(FIXTURES_DIR.iterdir()):
        if child.is_file():
            shutil.copy2(child, target / child.name)


def _force_offline_simple(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HKS_CONFIG_FILE", str(tmp_path / "missing.yaml"))
    monkeypatch.setenv("HKS_CONFIG_ENV", str(tmp_path / "missing.env"))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")
    monkeypatch.setenv("HKS_ROUTING_MODEL", "simple")
    monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "0")
    monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("hks.core.text_models.simple_embed", _stable_simple_embed)


def _stable_simple_embed(texts: list[str], *, dimensions: int = 128) -> list[list[float]]:
    from hks.core.text_models import simple_tokenize

    embeddings: list[list[float]] = []
    for text in texts:
        vector = [0.0] * dimensions
        for token in simple_tokenize(text, lowercase=True):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            vector[int.from_bytes(digest, "big") % dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        embeddings.append(vector)
    return embeddings


def _install_enriched_page_tree_summary(ks_root: Path) -> None:
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
def ingested_golden_ks_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _force_offline_simple(monkeypatch, tmp_path)
    docs_dir = tmp_path / "docs"
    _copy_fixture_files(docs_dir)

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(docs_dir)])
    assert result.exit_code == 0, result.stdout

    ks_root = tmp_path / "ks"
    _install_enriched_page_tree_summary(ks_root)
    return ks_root


def test_golden_retrieval_quality_gate(ingested_golden_ks_root: Path) -> None:
    cases = load_golden_cases(EVAL_PATH)
    observations: list[QueryObservation] = []

    for case in cases:
        response = query_run(case.question, writeback="no")
        observations.append(QueryObservation(case=case, payload=response.to_dict()))

    report = compute_metrics(observations)

    assert_thresholds(
        report,
        MetricThresholds(
            route_accuracy=0.70,
            precision_at_1=0.70,
            evidence_hit_rate=0.80,
            answer_contains_rate=1.00,
            no_hit_precision=1.00,
            writeback_false_positive_rate=0.00,
        ),
    )
