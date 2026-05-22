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
from hks.evaluation.retrieval_quality import (
    MetricThresholds,
    QueryObservation,
    assert_thresholds,
    compute_metrics,
    load_golden_cases,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "evals" / "golden_queries"
QUICK_EVAL_PATH = EVAL_DIR / "quick.jsonl"
STRICT_EVAL_PATH = EVAL_DIR / "strict.jsonl"
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


def _write_strict_fixture_files(target: Path) -> None:
    (target / "nebula-arbitration.md").write_text(
        (
            "# Nebula Arbitration\n\n"
            "Background status uses the old arbitration label only.\n\n"
            "# Runtime Gate\n\n"
            "Runtime gate requires coordinator approval before the midnight cutover.\n\n"
            "# Routine Appendix\n\n"
            "Archive rotation is informational only.\n"
        ),
        encoding="utf-8",
    )
    (target / "policy-old.md").write_text(
        (
            "# Legacy Retention Policy\n\n"
            "The deprecated retention window is 30 days. This file is stale.\n"
        ),
        encoding="utf-8",
    )
    (target / "policy-current.md").write_text(
        (
            "# Authoritative Retention Policy\n\n"
            "The authoritative retention policy window is 90 days.\n"
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def ingested_golden_ks_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _force_offline_simple(monkeypatch, tmp_path)
    docs_dir = tmp_path / "docs"
    _copy_fixture_files(docs_dir)

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(docs_dir)])
    assert result.exit_code == 0, result.stdout

    ks_root = tmp_path / "ks"
    return ks_root


@pytest.fixture()
def strict_ingested_golden_ks_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _force_offline_simple(monkeypatch, tmp_path)
    docs_dir = tmp_path / "docs"
    _copy_fixture_files(docs_dir)
    _write_strict_fixture_files(docs_dir)

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", str(docs_dir)])
    assert result.exit_code == 0, result.stdout
    enrich = runner.invoke(
        app,
        [
            "pageindex",
            "enrich",
            "--source-relpath",
            "nebula-arbitration.md",
            "--mode",
            "store",
            "--provider",
            "fake",
            "--force",
        ],
    )
    assert enrich.exit_code == 0, enrich.stdout
    return tmp_path / "ks"


def test_golden_retrieval_quality_gate(ingested_golden_ks_root: Path) -> None:
    cases = load_golden_cases(QUICK_EVAL_PATH)
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


def test_golden_writeback_auto_ineligible_case_does_not_enqueue(
    ingested_golden_ks_root: Path,
) -> None:
    case = next(
        case
        for case in load_golden_cases(QUICK_EVAL_PATH)
        if case.id == "wiki-summary-atlas"
    )
    queue_dir = ingested_golden_ks_root / "writeback" / "queue"

    response = query_run(case.question, writeback="auto")
    payload = response.to_dict()
    writeback_step = next(
        step for step in payload["trace"]["steps"] if step["kind"] == "writeback"
    )

    assert case.writeback_allowed is False
    assert payload["writeback_eligible"] is False
    assert writeback_step["detail"]["status"] == "skipped-ineligible"
    assert sorted(queue_dir.glob("*.json")) == []


def test_strict_golden_retrieval_quality_gate(strict_ingested_golden_ks_root: Path) -> None:
    cases = load_golden_cases(STRICT_EVAL_PATH)
    observations: list[QueryObservation] = []

    for case in cases:
        response = query_run(case.question, writeback="no")
        observations.append(QueryObservation(case=case, payload=response.to_dict()))

    report = compute_metrics(observations)

    assert_thresholds(
        report,
        MetricThresholds(
            route_accuracy=1.00,
            precision_at_1=1.00,
            evidence_hit_rate=1.00,
            answer_contains_rate=1.00,
            trace_hit_rate=1.00,
            no_hit_precision=1.00,
            writeback_false_positive_rate=0.00,
            writeback_eligible_hit_rate=1.00,
        ),
    )
