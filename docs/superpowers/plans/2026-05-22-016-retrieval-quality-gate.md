# 016 Retrieval Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic CI-grade golden retrieval quality gate that measures route accuracy, precision@1, evidence hit rate, no-hit precision, and writeback false-positive rate.

**Architecture:** Keep existing hosted evals unchanged. Add a small offline evaluation module under `src/hks/evaluation/` that computes metrics from `QueryResponse` payloads, then add a deterministic pytest runner over `evals/golden_queries/quick.jsonl` using `HKS_EMBEDDING_MODEL=simple`, RRF, and the existing fixture corpus. Wire the quick gate into CI after the ordinary test suite.

**Tech Stack:** Python 3.12, dataclasses, existing `typer` test runner pattern, existing `hks.commands.query.run`, existing `tests/fixtures/valid` corpus.

**Spec:** `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md` § 016.

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `src/hks/evaluation/__init__.py` | Evaluation package marker |
| `src/hks/evaluation/retrieval_quality.py` | Golden query case model, observation model, metric computation, threshold assertions |
| `tests/unit/evaluation/__init__.py` | Unit-test package marker |
| `tests/unit/evaluation/test_retrieval_quality.py` | Metric computation and threshold unit tests |
| `evals/golden_queries/quick.jsonl` | Deterministic offline golden query cases |
| `tests/eval/test_golden_retrieval_quality.py` | Offline CI gate runner over fixture runtime |

### Modified Files

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | Add targeted golden retrieval quality gate after `Test` |
| `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md` | Mark 016 implemented after completion |
| `docs/main.md` | Mention the quick golden retrieval gate under verification / retrieval quality |
| `README.md` / `README.en.md` | Add the new quality-gate command to developer verification |

---

## Task 1: Metric Module

**Files:**
- Create: `src/hks/evaluation/__init__.py`
- Create: `src/hks/evaluation/retrieval_quality.py`
- Create: `tests/unit/evaluation/__init__.py`
- Create: `tests/unit/evaluation/test_retrieval_quality.py`

- [x] **Step 1: Write failing unit tests for metric computation**

Create `tests/unit/evaluation/__init__.py` as an empty file.

Create `tests/unit/evaluation/test_retrieval_quality.py`:

```python
"""Unit tests for golden retrieval quality metrics."""

from __future__ import annotations

import pytest

from hks.evaluation.retrieval_quality import (
    GoldenQueryCase,
    MetricThresholds,
    QueryObservation,
    assert_thresholds,
    compute_metrics,
    evidence_matches,
)


def test_evidence_matches_relpath_and_quote_case_insensitive() -> None:
    payload = {
        "evidence": [
            {
                "source_relpath": "project-atlas.txt",
                "route": "wiki",
                "quote": "Project Atlas 目前處於設計收斂階段。",
            }
        ]
    }

    assert evidence_matches(
        payload,
        expected_source_relpath="project-atlas.txt",
        expected_evidence_quote="atlas",
    )


def test_evidence_match_fails_when_quote_missing() -> None:
    payload = {
        "evidence": [
            {
                "source_relpath": "project-atlas.txt",
                "route": "wiki",
                "quote": "Project Atlas 目前處於設計收斂階段。",
            }
        ]
    }

    assert not evidence_matches(
        payload,
        expected_source_relpath="project-atlas.txt",
        expected_evidence_quote="coordinator approval",
    )


def test_compute_metrics_counts_route_precision_evidence_no_hit_and_writeback() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="wiki-summary",
                question="Atlas 摘要",
                expected_route="wiki",
                expected_source_relpath="project-atlas.txt",
                expected_evidence_quote="Atlas",
                writeback_allowed=False,
            ),
            payload={
                "answer": "Project Atlas summary",
                "source": ["wiki"],
                "confidence": 1.0,
                "writeback_eligible": False,
                "evidence": [
                    {
                        "source_relpath": "project-atlas.txt",
                        "route": "wiki",
                        "quote": "Project Atlas summary",
                    }
                ],
                "trace": {"route": "wiki", "steps": []},
            },
        ),
        QueryObservation(
            case=GoldenQueryCase(
                id="no-hit",
                question="Zephyr Lime Thermostat",
                expected_route=None,
                expect_no_hit=True,
                writeback_allowed=False,
            ),
            payload={
                "answer": "未能於現有知識中找到答案",
                "source": [],
                "confidence": 0.0,
                "trace": {"route": "vector", "steps": []},
            },
        ),
        QueryObservation(
            case=GoldenQueryCase(
                id="bad-vector",
                question="detail owner",
                expected_route="vector",
                expected_source_relpath="owner.txt",
                expected_evidence_quote="Owner Iris",
                writeback_allowed=False,
            ),
            payload={
                "answer": "Owner Iris",
                "source": ["vector"],
                "confidence": 0.9,
                "writeback_eligible": True,
                "evidence": [
                    {
                        "source_relpath": "owner.txt",
                        "route": "vector",
                        "quote": "Owner Iris",
                    }
                ],
                "trace": {"route": "vector", "steps": []},
            },
        ),
    ]

    report = compute_metrics(observations)

    assert report.total == 3
    assert report.route_accuracy == 1.0
    assert report.precision_at_1 == 1.0
    assert report.evidence_hit_rate == 1.0
    assert report.no_hit_precision == 1.0
    assert report.writeback_false_positive_rate == pytest.approx(1 / 3)
    assert report.failures["writeback_false_positive"] == ["bad-vector"]


def test_assert_thresholds_raises_with_specific_metric_name() -> None:
    observations = [
        QueryObservation(
            case=GoldenQueryCase(
                id="route-miss",
                question="Atlas 摘要",
                expected_route="wiki",
                expected_source_relpath="project-atlas.txt",
                expected_evidence_quote="Atlas",
                writeback_allowed=False,
            ),
            payload={
                "answer": "wrong",
                "source": ["vector"],
                "confidence": 0.9,
                "writeback_eligible": False,
                "evidence": [],
                "trace": {"route": "vector", "steps": []},
            },
        )
    ]
    report = compute_metrics(observations)

    with pytest.raises(AssertionError, match="route_accuracy"):
        assert_thresholds(
            report,
            MetricThresholds(
                route_accuracy=1.0,
                precision_at_1=0.0,
                evidence_hit_rate=0.0,
                no_hit_precision=0.0,
                writeback_false_positive_rate=1.0,
            ),
        )
```

Run: `uv run pytest tests/unit/evaluation/test_retrieval_quality.py -q`

Expected: fails with `ModuleNotFoundError: No module named 'hks.evaluation'`.

- [x] **Step 2: Implement metric dataclasses and helpers**

Create `src/hks/evaluation/__init__.py` as an empty file.

Create `src/hks/evaluation/retrieval_quality.py`:

```python
"""Deterministic golden-query retrieval quality metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from hks.core.schema import Route


@dataclass(frozen=True, slots=True)
class GoldenQueryCase:
    id: str
    question: str
    expected_route: Route | None = None
    expected_source_relpath: str | None = None
    expected_evidence_quote: str | None = None
    expected_answer_contains: str | None = None
    writeback_allowed: bool = False
    expect_no_hit: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GoldenQueryCase:
        route = payload.get("expected_route")
        if route is not None and route not in {"wiki", "graph", "vector", "page_tree"}:
            raise ValueError(f"invalid expected_route for {payload.get('id')}: {route}")
        return cls(
            id=str(payload["id"]),
            question=str(payload["question"]),
            expected_route=cast(Route | None, route),
            expected_source_relpath=_optional_str(payload.get("expected_source_relpath")),
            expected_evidence_quote=_optional_str(payload.get("expected_evidence_quote")),
            expected_answer_contains=_optional_str(payload.get("expected_answer_contains")),
            writeback_allowed=bool(payload.get("writeback_allowed", False)),
            expect_no_hit=bool(payload.get("expect_no_hit", False)),
        )


@dataclass(frozen=True, slots=True)
class QueryObservation:
    case: GoldenQueryCase
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MetricThresholds:
    route_accuracy: float = 0.70
    precision_at_1: float = 0.70
    evidence_hit_rate: float = 0.80
    no_hit_precision: float = 1.00
    writeback_false_positive_rate: float = 0.00


@dataclass(frozen=True, slots=True)
class MetricReport:
    total: int
    route_accuracy: float
    precision_at_1: float
    evidence_hit_rate: float
    no_hit_precision: float
    writeback_false_positive_rate: float
    failures: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "route_accuracy": self.route_accuracy,
            "precision_at_1": self.precision_at_1,
            "evidence_hit_rate": self.evidence_hit_rate,
            "no_hit_precision": self.no_hit_precision,
            "writeback_false_positive_rate": self.writeback_false_positive_rate,
            "failures": self.failures,
        }


def load_golden_cases(path: Path) -> list[GoldenQueryCase]:
    cases: list[GoldenQueryCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            cases.append(GoldenQueryCase.from_dict(payload))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid golden query case at {path}:{line_no}: {exc}") from exc
    return cases


def evidence_matches(
    payload: dict[str, Any],
    *,
    expected_source_relpath: str | None,
    expected_evidence_quote: str | None,
) -> bool:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return expected_source_relpath is None and expected_evidence_quote is None

    for item in evidence:
        if not isinstance(item, dict):
            continue
        if (
            expected_source_relpath is not None
            and item.get("source_relpath") != expected_source_relpath
        ):
            continue
        quote = str(item.get("quote", ""))
        if expected_evidence_quote is not None:
            if expected_evidence_quote.casefold() not in quote.casefold():
                continue
        return True
    return False


def compute_metrics(observations: list[QueryObservation]) -> MetricReport:
    failures: dict[str, list[str]] = {
        "route_accuracy": [],
        "precision_at_1": [],
        "evidence_hit_rate": [],
        "no_hit_precision": [],
        "writeback_false_positive": [],
    }

    route_total = route_correct = 0
    precision_total = precision_correct = 0
    evidence_total = evidence_correct = 0
    no_hit_total = no_hit_correct = 0
    writeback_disallowed_total = writeback_false_positive = 0

    for observation in observations:
        case = observation.case
        payload = observation.payload
        source = payload.get("source")
        first_source = source[0] if isinstance(source, list) and source else None

        if case.expect_no_hit:
            no_hit_total += 1
            if source == [] and float(payload.get("confidence", 0.0)) == 0.0:
                no_hit_correct += 1
            else:
                failures["no_hit_precision"].append(case.id)
        elif case.expected_route is not None:
            route_total += 1
            if first_source == case.expected_route and payload.get("trace", {}).get("route") == case.expected_route:
                route_correct += 1
            else:
                failures["route_accuracy"].append(case.id)

        if case.expected_source_relpath is not None:
            precision_total += 1
            if _first_evidence_source(payload) == case.expected_source_relpath:
                precision_correct += 1
            else:
                failures["precision_at_1"].append(case.id)

        if case.expected_evidence_quote is not None or case.expected_source_relpath is not None:
            evidence_total += 1
            if evidence_matches(
                payload,
                expected_source_relpath=case.expected_source_relpath,
                expected_evidence_quote=case.expected_evidence_quote,
            ):
                evidence_correct += 1
            else:
                failures["evidence_hit_rate"].append(case.id)

        if not case.writeback_allowed:
            writeback_disallowed_total += 1
            if bool(payload.get("writeback_eligible")) or _auto_committed(payload):
                writeback_false_positive += 1
                failures["writeback_false_positive"].append(case.id)

    return MetricReport(
        total=len(observations),
        route_accuracy=_ratio(route_correct, route_total),
        precision_at_1=_ratio(precision_correct, precision_total),
        evidence_hit_rate=_ratio(evidence_correct, evidence_total),
        no_hit_precision=_ratio(no_hit_correct, no_hit_total),
        writeback_false_positive_rate=_ratio(
            writeback_false_positive,
            writeback_disallowed_total,
        ),
        failures={key: value for key, value in failures.items() if value},
    )


def assert_thresholds(report: MetricReport, thresholds: MetricThresholds) -> None:
    checks = {
        "route_accuracy": (report.route_accuracy, thresholds.route_accuracy, ">="),
        "precision_at_1": (report.precision_at_1, thresholds.precision_at_1, ">="),
        "evidence_hit_rate": (report.evidence_hit_rate, thresholds.evidence_hit_rate, ">="),
        "no_hit_precision": (report.no_hit_precision, thresholds.no_hit_precision, ">="),
        "writeback_false_positive_rate": (
            report.writeback_false_positive_rate,
            thresholds.writeback_false_positive_rate,
            "<=",
        ),
    }
    failures: list[str] = []
    for name, (actual, expected, op) in checks.items():
        if op == ">=" and actual < expected:
            failures.append(f"{name}: {actual:.3f} < {expected:.3f}")
        if op == "<=" and actual > expected:
            failures.append(f"{name}: {actual:.3f} > {expected:.3f}")
    if failures:
        raise AssertionError(
            "retrieval quality gate failed: "
            + "; ".join(failures)
            + f"; failing_cases={report.failures}"
        )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _first_evidence_source(payload: dict[str, Any]) -> str | None:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return None
    first = evidence[0]
    if not isinstance(first, dict):
        return None
    value = first.get("source_relpath")
    return value if isinstance(value, str) else None


def _auto_committed(payload: dict[str, Any]) -> bool:
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        return False
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") != "writeback":
            continue
        detail = step.get("detail")
        if isinstance(detail, dict) and detail.get("status") == "auto-committed":
            return True
    return False


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
```

Run: `uv run pytest tests/unit/evaluation/test_retrieval_quality.py -q`

Expected: all tests pass.

- [x] **Step 3: Verify metric module**

Run:

```bash
uv run pytest tests/unit/evaluation/test_retrieval_quality.py -q
uv run ruff check src/hks/evaluation tests/unit/evaluation
uv run mypy src/hks/evaluation
```

Expected: all pass.

---

## Task 2: Golden Query Fixture And CI Runner

**Files:**
- Create: `evals/golden_queries/quick.jsonl`
- Create: `tests/eval/test_golden_retrieval_quality.py`

- [x] **Step 1: Add deterministic golden query cases**

Create directory `evals/golden_queries/`.

Create `evals/golden_queries/quick.jsonl`:

```jsonl
{"id":"wiki-summary-atlas","question":"Atlas 摘要","expected_route":"wiki","expected_source_relpath":"project-atlas.txt","expected_evidence_quote":"Atlas","writeback_allowed":false}
{"id":"graph-impact-delay","question":"A 專案延遲影響哪些服務","expected_route":"graph","expected_source_relpath":"dependency-map.md","expected_evidence_quote":"checkout service","writeback_allowed":true}
{"id":"vector-clause-32","question":"clause 3.2 text","expected_route":"vector","expected_source_relpath":"clause-3-2.pdf","expected_evidence_quote":"architecture review","writeback_allowed":false}
{"id":"page-tree-nebula","question":"Nebula arbitration","expected_route":"page_tree","expected_source_relpath":"project-atlas.txt","expected_evidence_quote":"coordinator approval","writeback_allowed":true}
{"id":"no-hit-zephyr","question":"Zephyr Lime Thermostat","expected_route":null,"expect_no_hit":true,"writeback_allowed":false}
{"id":"graph-checkout-dependency","question":"checkout service 依賴什麼","expected_route":"graph","expected_source_relpath":"dependency-map.md","expected_evidence_quote":"pricing API","writeback_allowed":true}
```

- [x] **Step 2: Write the offline golden eval runner**

Create `tests/eval/test_golden_retrieval_quality.py`:

```python
"""Deterministic golden retrieval quality gate for CI."""

from __future__ import annotations

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
            no_hit_precision=1.00,
            writeback_false_positive_rate=0.00,
        ),
    )
```

Run: `uv run pytest tests/eval/test_golden_retrieval_quality.py -q`

Expected: passes in offline mode. If it fails, inspect `report.failures` from the assertion; do not lower `no_hit_precision` or `writeback_false_positive_rate`.

- [x] **Step 3: Verify eval runner with surrounding eval tests**

Run:

```bash
uv run pytest tests/eval/test_e2e_baseline_eval.py tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check tests/eval/test_golden_retrieval_quality.py
```

Expected: all pass.

---

## Task 3: Wire Quality Gate Into CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [x] **Step 1: Add CI step after the ordinary test suite**

Modify `.github/workflows/ci.yml` in the `test` job. Keep existing `Lint`, `Type check`, and `Test` steps. Add this step immediately after `Test`:

```yaml
      - name: Golden retrieval quality gate
        run: uv run pytest tests/eval/test_golden_retrieval_quality.py -q
```

Do not add an OpenAI key or `HKS_LLM_NETWORK_OPT_IN=1`; this gate must remain deterministic and offline.

- [x] **Step 2: Verify the CI command locally**

Run:

```bash
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
```

Expected: passes without hosted credentials.

---

## Task 4: Documentation Closeout

**Files:**
- Modify: `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md`
- Modify: `docs/main.md`
- Modify: `README.md`
- Modify: `README.en.md`

- [x] **Step 1: Mark 016 implemented in the design spec**

Under the 016 tests list in `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md`, add:

```markdown
> **Status:** Implemented — see `docs/superpowers/plans/2026-05-22-016-retrieval-quality-gate.md`.
```

- [x] **Step 2: Document the local quality-gate command**

In `README.md` under developer checks, add:

```bash
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
```

In `README.en.md`, add the same command under developer checks.

- [x] **Step 3: Update architecture docs**

In `docs/main.md` near fused retrieval, add:

```markdown
016 adds a deterministic golden retrieval quality gate under `tests/eval/test_golden_retrieval_quality.py`. It runs offline with `simple` backends and measures route accuracy, precision@1, evidence hit rate, no-hit precision, and writeback false-positive rate.
```

- [x] **Step 4: Verify docs and tests**

Run:

```bash
uv run pytest tests/unit/evaluation tests/eval/test_golden_retrieval_quality.py -q
uv run ruff check .
uv run mypy src/hks
```

Expected: all pass.

---

## Task 5: Final Verification

- [x] **Step 1: Full local gate**

Run:

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

Expected: all pass.

- [x] **Step 2: Focused quality evidence**

Run:

```bash
uv run pytest tests/eval/test_golden_retrieval_quality.py -q
```

Expected: all pass.

- [ ] **Step 3: Commit** (skipped: no commit/stage requested for this run)

```bash
git add \
  .github/workflows/ci.yml \
  README.md README.en.md docs/main.md \
  docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md \
  docs/superpowers/plans/2026-05-22-016-retrieval-quality-gate.md \
  evals/golden_queries/quick.jsonl \
  src/hks/evaluation \
  tests/unit/evaluation \
  tests/eval/test_golden_retrieval_quality.py
git commit -m "feat(016): add deterministic retrieval quality gate"
```

---

## Risk Notes

1. `no_hit_precision` and `writeback_false_positive_rate` are hard gates. Do not lower them to absorb flaky cases; fix ambiguous questions or route/writeback behavior.
2. The golden gate intentionally uses `writeback="no"` to avoid mutating the shared eval runtime while still inspecting `writeback_eligible`.
3. Hosted OpenAI evals remain opt-in. 016 must not make CI depend on secrets.
4. If `vector-clause-32` causes `evidence_hit_rate` instability under `simple`, inspect `_vector_hit_is_relevant()` before changing thresholds.
