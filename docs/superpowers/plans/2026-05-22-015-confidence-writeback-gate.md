# 015 Confidence and Writeback Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Separate raw retrieval score from calibrated confidence, add per-route writeback eligibility policies, make rerank fallback explicit in trace, and write forced writeback events to coordination log. After 015, `writeback=auto` never writes back unless the winning route's evidence meets its policy, and `writeback=yes` always records a `"forced": true` audit trail.

**Architecture:** Add `src/hks/retrieval/confidence.py` (already at 017 target path) for route-specific assessment. Modify `writeback/gate.py` to accept `ConfidenceAssessment` instead of raw `confidence: float`. Extend `QueryResponse` schema with additive-only optional fields (`retrieval_score`, `calibrated_confidence`, `writeback_eligible`). Make `_llm_rerank` fallback produce a structured `rerank` trace step with failure reason. Write forced writeback events to `coordination/events.jsonl`.

**Tech Stack:** Python 3.12, dataclasses, existing `hks.core.schema`, existing `hks.writeback`, existing `hks.coordination.store`.

**Spec:** `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md` § 015

---

## File Map

### New Files

| File | Responsibility |
|------|----------------|
| `src/hks/retrieval/__init__.py` | Package init |
| `src/hks/retrieval/confidence.py` | `ConfidenceAssessment` dataclass + `assess()` route-policy function |
| `tests/unit/retrieval/__init__.py` | Package init |
| `tests/unit/retrieval/test_confidence.py` | Route-specific eligibility unit tests |
| `tests/unit/writeback/test_gate_assessment.py` | Gate tests with `ConfidenceAssessment` input |

### Modified Files

| File | Change |
|------|--------|
| `src/hks/core/schema.py` | Add `retrieval_score`, `calibrated_confidence`, `writeback_eligible` optional fields to `QueryResponse`; add `"rerank"` to `TraceKind` |
| `specs/005-phase3-lint-impl/contracts/query-response.schema.json` | Add optional `retrieval_score`, `calibrated_confidence`, `writeback_eligible` properties; add `"rerank"` to trace step kind enum |
| `src/hks/writeback/gate.py` | `decide()` accepts `ConfidenceAssessment`; `flag="auto"` reads `calibrated_confidence` + `writeback_eligible`; `flag="yes"` marks `forced=True` |
| `src/hks/writeback/writer.py` | `commit()` accepts `forced: bool`, includes `"forced": true` in trace detail when set |
| `src/hks/commands/query.py` | Call `assess()` after rerank, populate new response fields, pass assessment to `decide()`, write forced writeback to coordination log, make `_llm_rerank` emit structured rerank trace step |
| `src/hks/storage/wiki.py` | Add `"forced-committed"` to `EventStatus` literal |
| `tests/unit/writeback/test_gate.py` | Update existing parametrize to use `ConfidenceAssessment` |
| `tests/integration/test_writeback.py` | Update monkeypatched `decide` calls; add test for forced writeback audit trail |
| `tests/unit/commands/test_fused_retrieval.py` | Add test for rerank fallback trace step |
| `tests/contract/test_query_phase1_contract_preserved.py` | Verify old `confidence` field unchanged |

---

## Task 1: ConfidenceAssessment Module

**Files:**
- Create: `src/hks/retrieval/__init__.py`
- Create: `src/hks/retrieval/confidence.py`
- Create: `tests/unit/retrieval/__init__.py`
- Create: `tests/unit/retrieval/test_confidence.py`

- [x] **Step 1: Write failing unit tests for route-specific eligibility**

Create `tests/unit/retrieval/__init__.py` (empty) and `tests/unit/retrieval/test_confidence.py`:

```python
"""Unit tests for route-specific confidence assessment."""

from __future__ import annotations

import pytest

from hks.retrieval.confidence import ConfidenceAssessment, assess


class TestAssessWiki:
    """Wiki auto writeback is always ineligible (requires explicit --writeback=yes)."""

    def test_wiki_high_confidence_still_ineligible(self) -> None:
        result = assess(
            route="wiki",
            raw_score=1.0,
            evidence=[{"source_relpath": "atlas.md", "route": "wiki", "quote": "Atlas summary"}],
        )
        assert isinstance(result, ConfidenceAssessment)
        assert result.retrieval_score == 1.0
        assert result.writeback_eligible is False
        assert any("wiki" in r.lower() for r in result.reasons)

    def test_wiki_zero_confidence(self) -> None:
        result = assess(route="wiki", raw_score=0.0, evidence=[])
        assert result.writeback_eligible is False
        assert result.calibrated_confidence == 0.0


class TestAssessGraph:
    """Graph auto writeback requires edge_ids, evidence_by_relpath, source_relpath, and threshold."""

    def test_graph_with_full_evidence_eligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"}],
            metadata={
                "edge_ids": ["e1"],
                "evidence_by_relpath": {"dep.md": "A impacts B"},
            },
        )
        assert result.writeback_eligible is True
        assert result.calibrated_confidence >= 0.75

    def test_graph_missing_edge_ids_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"}],
            metadata={"evidence_by_relpath": {"dep.md": "A impacts B"}},
        )
        assert result.writeback_eligible is False
        assert any("edge" in r.lower() for r in result.reasons)

    def test_graph_missing_evidence_by_relpath_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"}],
            metadata={"edge_ids": ["e1"]},
        )
        assert result.writeback_eligible is False

    def test_graph_empty_evidence_list_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[],
            metadata={"edge_ids": ["e1"], "evidence_by_relpath": {"dep.md": "text"}},
        )
        assert result.writeback_eligible is False

    def test_graph_below_threshold_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.3,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "weak"}],
            metadata={"edge_ids": ["e1"], "evidence_by_relpath": {"dep.md": "weak"}},
        )
        assert result.writeback_eligible is False


class TestAssessVector:
    """Vector auto writeback requires source_relpath, quote, similarity threshold, non-empty evidence."""

    def test_vector_with_full_evidence_eligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "fact text"}],
        )
        assert result.writeback_eligible is True

    def test_vector_missing_source_relpath_ineligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"route": "vector", "quote": "fact text"}],
        )
        assert result.writeback_eligible is False

    def test_vector_missing_quote_ineligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"source_relpath": "a.md", "route": "vector"}],
        )
        assert result.writeback_eligible is False

    def test_vector_below_similarity_threshold_ineligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.3,
            evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "low sim"}],
        )
        assert result.writeback_eligible is False

    def test_vector_empty_evidence_ineligible(self) -> None:
        result = assess(route="vector", raw_score=0.9, evidence=[])
        assert result.writeback_eligible is False


class TestAssessPageTree:
    """Page tree auto writeback requires source_relpath, section_path, page_range, non-empty quote."""

    def test_page_tree_with_full_evidence_eligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "section content",
                    "section_path": "Chapter 1 > Intro",
                    "page_range": {"start": 1, "end": 3},
                }
            ],
        )
        assert result.writeback_eligible is True

    def test_page_tree_missing_section_path_ineligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "content",
                    "page_range": {"start": 1, "end": 3},
                }
            ],
        )
        assert result.writeback_eligible is False

    def test_page_tree_missing_page_range_ineligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "content",
                    "section_path": "Chapter 1",
                }
            ],
        )
        assert result.writeback_eligible is False

    def test_page_tree_empty_quote_ineligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "",
                    "section_path": "Ch1",
                    "page_range": {"start": 1, "end": 2},
                }
            ],
        )
        assert result.writeback_eligible is False


class TestAssessCalibration:
    """Calibrated confidence is clamped [0.0, 1.0] and is the same as raw score for now."""

    def test_calibrated_equals_raw_for_initial_release(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "text"}],
        )
        assert result.calibrated_confidence == result.retrieval_score

    def test_calibrated_clamped_at_zero(self) -> None:
        result = assess(route="wiki", raw_score=-0.5, evidence=[])
        assert result.calibrated_confidence >= 0.0

    def test_calibrated_clamped_at_one(self) -> None:
        result = assess(route="wiki", raw_score=1.5, evidence=[])
        assert result.calibrated_confidence <= 1.0

    def test_retrieval_score_equals_raw_score(self) -> None:
        result = assess(route="vector", raw_score=0.42, evidence=[])
        assert result.retrieval_score == 0.42
```

Run tests — all must fail with `ModuleNotFoundError`.

- [x] **Step 2: Implement ConfidenceAssessment and assess()**

Create `src/hks/retrieval/__init__.py` (empty) and `src/hks/retrieval/confidence.py`:

```python
"""Route-specific confidence assessment and writeback eligibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hks.core.schema import Route

# Per-route auto-writeback similarity/confidence threshold.
# Graph and vector need a meaningful minimum; wiki never auto-writes;
# page_tree uses a moderate bar.
_AUTO_THRESHOLDS: dict[Route, float] = {
    "wiki": 999.0,     # effectively never (wiki uses explicit writeback only)
    "graph": 0.75,
    "vector": 0.65,
    "page_tree": 0.50,
}


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    """Result of route-specific confidence assessment.

    Attributes:
        retrieval_score: Raw score from the winning candidate (= ``confidence``
            in the response, preserved for backward compatibility).
        calibrated_confidence: Calibrated confidence.  For the initial release
            this equals ``retrieval_score`` clamped to [0, 1]; a future
            calibration model may diverge.
        writeback_eligible: Whether this result passes the route-specific
            auto-writeback policy.  ``False`` blocks ``writeback=auto`` from
            committing.
        reasons: Human-readable list of reasons why eligibility is
            ``True`` or ``False``.
    """

    retrieval_score: float
    calibrated_confidence: float
    writeback_eligible: bool
    reasons: list[str] = field(default_factory=list)


def assess(
    *,
    route: Route,
    raw_score: float,
    evidence: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> ConfidenceAssessment:
    """Assess confidence and writeback eligibility for a winning candidate.

    The ``metadata`` dict carries route-specific extras that the candidate
    had (e.g. ``edge_ids``, ``evidence_by_relpath`` for graph).
    """
    retrieval_score = raw_score
    calibrated = max(0.0, min(1.0, raw_score))
    meta = metadata or {}

    if route == "wiki":
        return _assess_wiki(retrieval_score, calibrated)
    if route == "graph":
        return _assess_graph(retrieval_score, calibrated, evidence, meta)
    if route == "vector":
        return _assess_vector(retrieval_score, calibrated, evidence)
    if route == "page_tree":
        return _assess_page_tree(retrieval_score, calibrated, evidence)
    # Unknown route — ineligible by default
    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=False,
        reasons=[f"unknown route: {route}"],
    )


def _assess_wiki(
    retrieval_score: float, calibrated: float
) -> ConfidenceAssessment:
    """Wiki auto writeback is always ineligible — wiki is the write target."""
    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=False,
        reasons=["wiki route: auto writeback ineligible (use --writeback=yes)"],
    )


def _assess_graph(
    retrieval_score: float,
    calibrated: float,
    evidence: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> ConfidenceAssessment:
    """Graph requires edge_ids, evidence_by_relpath, source_relpath, and threshold."""
    reasons: list[str] = []
    eligible = True

    threshold = _AUTO_THRESHOLDS["graph"]
    if calibrated < threshold:
        eligible = False
        reasons.append(f"graph calibrated_confidence {calibrated:.2f} < threshold {threshold}")

    edge_ids = metadata.get("edge_ids")
    if not isinstance(edge_ids, list) or not edge_ids:
        eligible = False
        reasons.append("graph missing edge_ids")

    evidence_by_relpath = metadata.get("evidence_by_relpath")
    if not isinstance(evidence_by_relpath, dict) or not evidence_by_relpath:
        eligible = False
        reasons.append("graph missing evidence_by_relpath")

    if not evidence:
        eligible = False
        reasons.append("graph empty evidence list")
    else:
        has_relpath = any(
            isinstance(e.get("source_relpath"), str) and e["source_relpath"]
            for e in evidence
        )
        if not has_relpath:
            eligible = False
            reasons.append("graph evidence missing source_relpath")

    if eligible:
        reasons.append("graph route: all evidence requirements met")

    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=eligible,
        reasons=reasons,
    )


def _assess_vector(
    retrieval_score: float,
    calibrated: float,
    evidence: list[dict[str, Any]],
) -> ConfidenceAssessment:
    """Vector requires source_relpath, quote, similarity threshold, non-empty evidence."""
    reasons: list[str] = []
    eligible = True

    threshold = _AUTO_THRESHOLDS["vector"]
    if calibrated < threshold:
        eligible = False
        reasons.append(f"vector calibrated_confidence {calibrated:.2f} < threshold {threshold}")

    if not evidence:
        eligible = False
        reasons.append("vector empty evidence list")
    else:
        first = evidence[0]
        if not isinstance(first.get("source_relpath"), str) or not first["source_relpath"]:
            eligible = False
            reasons.append("vector evidence missing source_relpath")
        if not isinstance(first.get("quote"), str) or not first["quote"]:
            eligible = False
            reasons.append("vector evidence missing quote")

    if eligible:
        reasons.append("vector route: all evidence requirements met")

    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=eligible,
        reasons=reasons,
    )


def _assess_page_tree(
    retrieval_score: float,
    calibrated: float,
    evidence: list[dict[str, Any]],
) -> ConfidenceAssessment:
    """Page tree requires source_relpath, section_path, page_range, non-empty quote."""
    reasons: list[str] = []
    eligible = True

    threshold = _AUTO_THRESHOLDS["page_tree"]
    if calibrated < threshold:
        eligible = False
        reasons.append(
            f"page_tree calibrated_confidence {calibrated:.2f} < threshold {threshold}"
        )

    if not evidence:
        eligible = False
        reasons.append("page_tree empty evidence list")
    else:
        first = evidence[0]
        if not isinstance(first.get("source_relpath"), str) or not first["source_relpath"]:
            eligible = False
            reasons.append("page_tree evidence missing source_relpath")
        if not isinstance(first.get("quote"), str) or not first["quote"]:
            eligible = False
            reasons.append("page_tree evidence missing non-empty quote")
        if not isinstance(first.get("section_path"), str) or not first["section_path"]:
            eligible = False
            reasons.append("page_tree evidence missing section_path")
        if not isinstance(first.get("page_range"), dict):
            eligible = False
            reasons.append("page_tree evidence missing page_range")

    if eligible:
        reasons.append("page_tree route: all evidence requirements met")

    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=eligible,
        reasons=reasons,
    )
```

Run tests — all must pass.

- [x] **Step 3: Verify**

```bash
uv run pytest tests/unit/retrieval/ -v
uv run ruff check src/hks/retrieval/
uv run mypy src/hks/retrieval/
```

---

## Task 2: Schema Evolution (Additive-Only)

**Files:**
- Modify: `src/hks/core/schema.py`
- Modify: `specs/005-phase3-lint-impl/contracts/query-response.schema.json`
- Modify: `tests/contract/test_query_phase1_contract_preserved.py`

- [x] **Step 1: Add optional fields to QueryResponse dataclass**

In `src/hks/core/schema.py`:

1. Add `"rerank"` to `TraceKind` literal.
2. Add three optional fields to `QueryResponse`:
   ```python
   retrieval_score: float | None = None
   calibrated_confidence: float | None = None
   writeback_eligible: bool | None = None
   ```
3. Update `to_dict()` to include them when not `None`:
   ```python
   if self.retrieval_score is not None:
       payload["retrieval_score"] = self.retrieval_score
   if self.calibrated_confidence is not None:
       payload["calibrated_confidence"] = self.calibrated_confidence
   if self.writeback_eligible is not None:
       payload["writeback_eligible"] = self.writeback_eligible
   ```

- [x] **Step 2: Update JSON schema contract**

In `specs/005-phase3-lint-impl/contracts/query-response.schema.json`:

1. Add `"rerank"` to `$defs.traceStep.properties.kind.enum`.
2. Add to top-level `properties` (not `required`):
   ```json
   "retrieval_score": {
     "type": "number",
     "minimum": 0.0,
     "maximum": 1.0
   },
   "calibrated_confidence": {
     "type": "number",
     "minimum": 0.0,
     "maximum": 1.0
   },
   "writeback_eligible": {
     "type": "boolean"
   }
   ```
3. Update the `description` field to note 015 additions.

- [x] **Step 3: Add contract test for new optional fields**

Add to `tests/contract/test_query_phase1_contract_preserved.py` (or create new `tests/contract/test_015_confidence_fields.py` if cleaner):

```python
def test_confidence_fields_optional_and_valid() -> None:
    """Old payloads without new fields still validate; new payloads with fields also validate."""
    from hks.core.schema import validate

    # Old payload (no new fields)
    old_payload = {
        "answer": "test",
        "source": ["wiki"],
        "confidence": 0.8,
        "trace": {"route": "wiki", "steps": []},
    }
    validate(old_payload)

    # New payload with all optional fields
    new_payload = {
        **old_payload,
        "retrieval_score": 0.8,
        "calibrated_confidence": 0.8,
        "writeback_eligible": True,
    }
    validate(new_payload)
```

- [x] **Step 4: Verify**

```bash
uv run pytest tests/contract/ -v -k "phase1 or confidence"
uv run ruff check src/hks/core/schema.py
uv run mypy src/hks/core/schema.py
```

---

## Task 3: Writeback Gate Refactor

**Files:**
- Modify: `src/hks/writeback/gate.py`
- Modify: `src/hks/storage/wiki.py`
- Create: `tests/unit/writeback/test_gate_assessment.py`
- Modify: `tests/unit/writeback/test_gate.py`

- [x] **Step 1: Add `"forced-committed"` to EventStatus**

In `src/hks/storage/wiki.py`, add `"forced-committed"` to the `EventStatus` literal union.

- [x] **Step 2: Write failing tests for new gate behavior**

Create `tests/unit/writeback/test_gate_assessment.py`:

```python
"""Tests for writeback gate with ConfidenceAssessment."""

from __future__ import annotations

from typing import cast

import pytest

from hks.retrieval.confidence import ConfidenceAssessment
from hks.writeback.gate import WritebackFlag, decide


def _eligible(score: float = 0.9) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=score,
        calibrated_confidence=score,
        writeback_eligible=True,
        reasons=["test eligible"],
    )


def _ineligible(score: float = 0.9) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=score,
        calibrated_confidence=score,
        writeback_eligible=False,
        reasons=["test ineligible"],
    )


class TestDecideWithAssessment:
    def test_auto_eligible_above_threshold_commits(self) -> None:
        decision = decide("auto", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "commit"
        assert decision.status == "auto-committed"

    def test_auto_ineligible_despite_high_score_declines(self) -> None:
        decision = decide("auto", assessment=_ineligible(0.99), is_tty=False)
        assert decision.action == "decline"
        assert decision.status == "auto-skipped-ineligible"

    def test_auto_eligible_below_threshold_declines(self) -> None:
        decision = decide("auto", assessment=_eligible(0.3), is_tty=False)
        assert decision.action == "decline"
        assert decision.status == "auto-skipped-low-confidence"

    def test_yes_forces_commit_regardless_of_eligibility(self) -> None:
        decision = decide("yes", assessment=_ineligible(0.1), is_tty=False)
        assert decision.action == "commit"
        assert decision.status == "forced-committed"
        assert decision.forced is True

    def test_yes_with_eligible_still_forced(self) -> None:
        decision = decide("yes", assessment=_eligible(0.9), is_tty=True)
        assert decision.forced is True

    def test_no_always_declines(self) -> None:
        decision = decide("no", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "decline"

    def test_ask_non_tty_skips(self) -> None:
        decision = decide("ask", assessment=_eligible(0.9), is_tty=False)
        assert decision.action == "skip-non-tty"


class TestDecideBackwardCompat:
    """decide() still works with confidence kwarg for callers not yet migrated."""

    def test_confidence_kwarg_still_works(self) -> None:
        decision = decide("auto", confidence=0.9, is_tty=False)
        assert decision.action == "commit"
        assert decision.status == "auto-committed"

    def test_confidence_kwarg_low_declines(self) -> None:
        decision = decide("auto", confidence=0.2, is_tty=False)
        assert decision.action == "decline"
```

- [x] **Step 3: Refactor decide()**

Modify `src/hks/writeback/gate.py`:

```python
"""Write-back decision helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import typer

from hks.core.config import config_value
from hks.storage.wiki import EventStatus

if TYPE_CHECKING:
    from hks.retrieval.confidence import ConfidenceAssessment

type WritebackFlag = Literal["auto", "yes", "no", "ask"]
type DecisionAction = Literal["commit", "decline", "skip-non-tty"]


@dataclass(frozen=True, slots=True)
class Decision:
    action: DecisionAction
    status: EventStatus
    forced: bool = False


def prompt_user() -> bool:
    return bool(typer.confirm("回寫 wiki?", default=False))


def auto_threshold() -> float:
    return float(config_value("HKS_WRITEBACK_AUTO_THRESHOLD") or "0.75")


def decide(
    flag: WritebackFlag,
    *,
    assessment: ConfidenceAssessment | None = None,
    confidence: float | None = None,
    is_tty: bool,
    prompt: Callable[[], bool] | None = None,
) -> Decision:
    if flag == "yes":
        return Decision(action="commit", status="forced-committed", forced=True)
    if flag == "no":
        return Decision(action="decline", status="declined")
    if flag == "auto":
        if assessment is not None:
            return _decide_auto_with_assessment(assessment)
        # Backward-compatible path: raw confidence only
        raw = confidence if confidence is not None else 0.0
        if raw >= auto_threshold():
            return Decision(action="commit", status="auto-committed")
        return Decision(action="decline", status="auto-skipped-low-confidence")
    # flag == "ask"
    if not is_tty:
        return Decision(action="skip-non-tty", status="skip-non-tty")
    confirmed = prompt() if prompt is not None else prompt_user()
    if confirmed:
        return Decision(action="commit", status="committed")
    return Decision(action="decline", status="declined")


def _decide_auto_with_assessment(assessment: ConfidenceAssessment) -> Decision:
    if not assessment.writeback_eligible:
        return Decision(action="decline", status="auto-skipped-ineligible")
    if assessment.calibrated_confidence >= auto_threshold():
        return Decision(action="commit", status="auto-committed")
    return Decision(action="decline", status="auto-skipped-low-confidence")
```

**Key design decisions:**
- `flag="yes"` always produces `forced=True` and `status="forced-committed"` — this is the audit trail.
- `flag="auto"` checks `writeback_eligible` first (route policy), then `calibrated_confidence >= threshold`.
- Backward compat: `confidence` kwarg still works when `assessment` is `None`.

- [x] **Step 4: Update existing gate tests**

In `tests/unit/writeback/test_gate.py`, update parametrize entries:
- `("yes", ...)` → expected status becomes `"forced-committed"` (not `"committed"`).
- Add assertion for `decision.forced is True` when `flag="yes"`.

The change is:
```python
# Old:
("yes", 0.1, True, "committed"),
("yes", 0.1, False, "committed"),
# New:
("yes", 0.1, True, "forced-committed"),
("yes", 0.1, False, "forced-committed"),
```

And add to the assertion:
```python
if flag == "yes":
    assert decision.forced is True
```

- [x] **Step 5: Verify**

```bash
uv run pytest tests/unit/writeback/ -v
uv run ruff check src/hks/writeback/
uv run mypy src/hks/writeback/
```

---

## Task 4: Rerank Trace Step

**Files:**
- Modify: `src/hks/commands/query.py` (`_llm_rerank`, `_rerank_candidates`)
- Modify: `tests/unit/commands/test_fused_retrieval.py`

- [x] **Step 1: Write failing test for rerank fallback reason in trace**

Add to `tests/unit/commands/test_fused_retrieval.py`:

```python
class TestRerankTrace:
    def test_rrf_strategy_returns_rrf_with_none_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        candidates = [
            Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
        ]
        ranked, strategy, rerank_detail = _rerank_candidates("q", candidates)

        assert strategy == "rrf"
        assert rerank_detail["strategy"] == "rrf"
        assert rerank_detail.get("status") is None or rerank_detail["status"] == "primary"

    def test_llm_fallback_captures_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When LLM rerank is available but fails, detail must capture fallback reason."""
        monkeypatch.setenv("HKS_LLM_NETWORK_OPT_IN", "1")
        monkeypatch.setenv("HKS_LLM_PROVIDER_OPENAI_API_KEY", "sk-test")

        def mock_openai_chat(**kwargs):
            raise TimeoutError("mock timeout")

        monkeypatch.setattr("hks.commands.query._openai_chat", mock_openai_chat)

        candidates = [
            Candidate(text="a", source_route="wiki", score=1.0, metadata={}),
        ]
        ranked, strategy, rerank_detail = _rerank_candidates("q", candidates)

        assert strategy == "llm-rerank"
        assert rerank_detail["status"] == "fallback"
        assert rerank_detail["fallback_strategy"] == "rrf"
        assert isinstance(rerank_detail["reason"], str)
```

> **Note:** `_rerank_candidates` return signature changes from `tuple[list[Candidate], str]` to `tuple[list[Candidate], str, dict[str, object]]` — the third element is the rerank detail dict for the trace step.

- [x] **Step 2: Refactor _llm_rerank and _rerank_candidates**

In `src/hks/commands/query.py`:

1. Change `_llm_rerank` to return `tuple[list[Candidate], dict[str, object]]`:

```python
def _llm_rerank(
    question: str,
    candidates: list[Candidate],
) -> tuple[list[Candidate], dict[str, object]]:
    from hks.core.config import config_value
    from hks.llm.config import hosted_provider_ready
    from hks.llm.providers import _openai_chat

    if not hosted_provider_ready("openai"):
        return _rrf_rerank(candidates), {
            "strategy": "rrf",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": "provider_not_ready",
        }
    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if not api_key:
        return _rrf_rerank(candidates), {
            "strategy": "rrf",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": "credential_missing",
        }
    # ... (existing OpenAI call logic) ...

    try:
        result = _openai_chat(...)
        # ... (existing ranking logic) ...
        return ranked, {"strategy": "llm", "status": "success"}
    except TimeoutError:
        return _rrf_rerank(candidates), {
            "strategy": "llm",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": "openai_timeout",
        }
    except Exception as exc:
        reason = _classify_rerank_error(exc)
        return _rrf_rerank(candidates), {
            "strategy": "llm",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": reason,
        }
```

2. Add `_classify_rerank_error`:

```python
def _classify_rerank_error(exc: Exception) -> str:
    """Map rerank exception to a reason enum value."""
    import httpx
    if isinstance(exc, TimeoutError):
        return "openai_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "openai_http_error"
    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return "openai_invalid_json"
    if isinstance(exc, (KeyError, IndexError, TypeError)):
        return "openai_invalid_ranking"
    return "unexpected_error"
```

3. Change `_rerank_candidates` return to `tuple[list[Candidate], str, dict[str, object]]`:

```python
def _rerank_candidates(
    question: str,
    candidates: list[Candidate],
) -> tuple[list[Candidate], str, dict[str, object]]:
    from hks.llm.config import hosted_provider_ready

    if hosted_provider_ready("openai"):
        ranked, detail = _llm_rerank(question, candidates)
        return ranked, "llm-rerank", detail
    ranked = _rrf_rerank(candidates)
    return ranked, "rrf", {"strategy": "rrf", "status": "primary"}
```

4. In `run()`, update the caller to unpack the new return value and emit a `rerank` trace step alongside the existing `merge` step:

```python
ranked, strategy, rerank_detail = _rerank_candidates(question, all_candidates)
steps.append(
    TraceStep(
        kind="rerank",
        detail=rerank_detail,
    )
)
steps.append(
    TraceStep(
        kind="merge",
        detail={
            "strategy": strategy,
            "candidate_count": len(all_candidates),
            "top_candidate": {
                "route": ranked[0].source_route,
                "score": ranked[0].score,
            },
        },
    )
)
```

- [x] **Step 3: Update existing fused retrieval tests**

Existing tests that import `_rerank_candidates` need to unpack the third element:

```python
# Old:
ranked, strategy = _rerank_candidates("question", candidates)
# New:
ranked, strategy, _detail = _rerank_candidates("question", candidates)
```

- [x] **Step 4: Verify**

```bash
uv run pytest tests/unit/commands/test_fused_retrieval.py -v
uv run ruff check src/hks/commands/query.py
uv run mypy src/hks/commands/query.py
```

---

## Task 5: Wire Assessment into Query Pipeline

**Files:**
- Modify: `src/hks/commands/query.py` (`run()`, `_maybe_writeback()`)
- Modify: `src/hks/writeback/writer.py`

- [x] **Step 1: Import and call assess() in run()**

In `src/hks/commands/query.py`, after the winner is chosen and evidence is built:

```python
from hks.retrieval.confidence import assess

# ... after winner = ranked[0] ...
evidence = _candidate_evidence(winner)
assessment = assess(
    route=winner.source_route,
    raw_score=winner.score,
    evidence=evidence,
    metadata=dict(winner.metadata),
)

response = QueryResponse(
    answer=winner.text,
    source=[winner.source_route],
    confidence=winner.score,  # raw score — unchanged for backward compat
    trace=Trace(route=winner.source_route, steps=steps),
    evidence=evidence,
    retrieval_score=assessment.retrieval_score,
    calibrated_confidence=assessment.calibrated_confidence,
    writeback_eligible=assessment.writeback_eligible,
)
```

- [x] **Step 2: Pass assessment through _maybe_writeback()**

Change `_maybe_writeback` signature to accept `assessment`:

```python
def _maybe_writeback(
    *,
    question: str,
    response: QueryResponse,
    writeback: str,
    wiki_store: WikiStore,
    assessment: ConfidenceAssessment | None = None,
) -> QueryResponse:
```

Pass `assessment` to `decide()`:

```python
decision = decide(
    cast(WritebackFlag, writeback),
    assessment=assessment,
    confidence=response.confidence,  # backward compat fallback
    is_tty=sys.stdout.isatty(),
)
```

- [x] **Step 3: Update writer.py for forced writeback trace**

In `src/hks/writeback/writer.py`, add `forced: bool = False` param to `commit()`:

```python
def commit(
    *,
    query: str,
    response: QueryResponse,
    status: EventStatus = "committed",
    context: WritebackContext | None = None,
    wiki_store: WikiStore | None = None,
    forced: bool = False,
) -> list[TraceStep]:
```

In the returned `TraceStep`, include `"forced": True` when set:

```python
detail = {
    "status": status,
    "slug": page.slug,
    "path": f"pages/{page.slug}.md",
    "related": [related.slug for related in related_pages],
}
if forced:
    detail["forced"] = True
return [TraceStep(kind="writeback", detail=detail)]
```

- [x] **Step 4: Write forced writeback to coordination events.jsonl**

In `_maybe_writeback` in `src/hks/commands/query.py`, when `decision.forced` is True and commit succeeds, append to coordination log:

```python
if decision.forced:
    try:
        from hks.coordination.store import CoordinationStore
        coord_store = CoordinationStore(runtime_paths())
        coord_store.append_events([{
            "type": "forced_writeback",
            "timestamp": utc_now_iso(),
            "query": question,
            "route": response.trace.route,
            "confidence": response.confidence,
            "calibrated_confidence": response.calibrated_confidence,
            "writeback_eligible": response.writeback_eligible,
        }])
    except Exception:
        pass  # coordination is best-effort, don't fail the query
```

- [x] **Step 5: Pass `forced` and `assessment` through call chain**

In `_maybe_writeback`, when `decision.action == "commit"`, pass `forced=decision.forced`:

```python
response.trace.steps.extend(
    commit(
        query=question,
        response=response,
        status=decision.status,
        context=context,
        wiki_store=wiki_store,
        forced=decision.forced,
    )
)
```

- [x] **Step 6: Verify**

```bash
uv run pytest tests/unit/ tests/contract/ -v --tb=short
uv run ruff check src/hks/
uv run mypy src/hks/
```

---

## Task 6: Integration Tests

**Files:**
- Modify: `tests/integration/test_writeback.py`
- Modify: `tests/unit/writeback/test_gate.py` (already covered in Task 3)

- [x] **Step 1: Update existing writeback integration tests**

In `tests/integration/test_writeback.py`:

1. Update monkeypatched `decide` lambda signatures. The existing tests use:
   ```python
   lambda flag, confidence, is_tty: Decision(action="commit", status="committed")
   ```
   Change to match new signature (keyword-only args):
   ```python
   lambda flag, *, assessment=None, confidence=None, is_tty=False, prompt=None: Decision(
       action="commit", status="committed"
   )
   ```

2. Update `test_writeback_yes_overrides_non_tty` to verify `"forced": true` in writeback trace:
   ```python
   payload = json.loads(result.stdout)
   writeback_step = next(
       step for step in payload["trace"]["steps"] if step["kind"] == "writeback"
   )
   assert writeback_step["detail"].get("forced") is True
   assert writeback_step["detail"]["status"] == "forced-committed"
   ```

- [x] **Step 2: Add test for auto writeback blocked by ineligible assessment**

```python
@pytest.mark.integration
@pytest.mark.us3
def test_writeback_auto_declines_when_ineligible(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    """Wiki route is always ineligible for auto writeback after 015."""
    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=auto"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # Wiki route hit — always ineligible, so writeback should NOT commit
    if payload["source"] == ["wiki"]:
        writeback_step = next(
            step for step in payload["trace"]["steps"] if step["kind"] == "writeback"
        )
        assert writeback_step["detail"]["status"] in {
            "auto-skipped-ineligible",
            "declined",
        }
```

- [x] **Step 3: Add test for new optional fields in response**

```python
@pytest.mark.integration
def test_query_response_includes_015_confidence_fields(
    cli_runner, ingested_for_writeback
) -> None:
    result = cli_runner.invoke(app, ["query", "Project Atlas summary", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    # New optional fields must be present after 015
    assert "retrieval_score" in payload
    assert "calibrated_confidence" in payload
    assert "writeback_eligible" in payload
    assert isinstance(payload["retrieval_score"], (int, float))
    assert isinstance(payload["calibrated_confidence"], (int, float))
    assert isinstance(payload["writeback_eligible"], bool)
    # retrieval_score == confidence (raw score preserved)
    assert payload["retrieval_score"] == payload["confidence"]
```

- [x] **Step 4: Add test for rerank trace step in response**

```python
@pytest.mark.integration
def test_query_response_includes_rerank_trace_step(
    cli_runner, ingested_for_writeback
) -> None:
    result = cli_runner.invoke(app, ["query", "Project Atlas summary", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    rerank_steps = [s for s in payload["trace"]["steps"] if s["kind"] == "rerank"]
    assert len(rerank_steps) == 1
    assert "strategy" in rerank_steps[0]["detail"]
```

- [x] **Step 5: Verify**

```bash
uv run pytest tests/integration/test_writeback.py -v
uv run pytest tests/integration/ -v --tb=short -q
```

---

## Task 7: Adapter Test Updates

**Files:**
- Modify: various adapter test files that mock `decide` or assert writeback behavior

- [x] **Step 1: Grep and update all decide() call sites**

Search for all test files that call or mock `decide`:

```bash
grep -rn "decide" tests/ --include="*.py" | grep -v "__pycache__"
```

For each site that uses the old `lambda flag, confidence, is_tty:` signature, update to the keyword-only signature. Common patterns:

```python
# Old:
monkeypatch.setattr(query_command, "decide",
    lambda flag, confidence, is_tty: Decision(...))
# New:
monkeypatch.setattr(query_command, "decide",
    lambda flag, *, assessment=None, confidence=None, is_tty=False, prompt=None: Decision(...))
```

- [x] **Step 2: Update adapter error/writeback tests**

Tests in `tests/unit/adapters/test_errors.py` and `tests/unit/adapters/test_validation.py` that reference writeback status strings — update `"committed"` to `"forced-committed"` where the test uses `--writeback=yes`.

- [x] **Step 3: Verify full suite**

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

---

## Task 8: Documentation and Spec Update

**Files:**
- Modify: `docs/configuration.md`
- Modify: `docs/main.md` (if needed)
- Modify: `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md`

- [x] **Step 1: Document new response fields**

In `docs/main.md` or the appropriate section, update the response contract example to show the new optional fields:

```json
{
  "answer": "...",
  "source": ["wiki"],
  "confidence": 0.88,
  "retrieval_score": 0.88,
  "calibrated_confidence": 0.88,
  "writeback_eligible": false,
  "evidence": [...],
  "trace": {...}
}
```

- [x] **Step 2: Document HKS_WRITEBACK_AUTO_THRESHOLD interaction**

In `docs/configuration.md`, clarify that after 015:
- `HKS_WRITEBACK_AUTO_THRESHOLD` still controls the confidence floor.
- `writeback_eligible` is a route-specific prerequisite that must be true in addition to the threshold.
- `--writeback=yes` bypasses both checks but records `"forced": true`.

- [x] **Step 3: Mark 015 status in design spec**

In the design spec, after the 015 section, add a status note:

```
> **Status:** Implemented — see `015-confidence-writeback-gate` plan.
```

- [x] **Step 4: Verify docs consistency**

Manually review that `docs/main.md` response example, `CLAUDE.md` "Stable contracts" section, and the JSON schema all agree on the new optional fields.

---

## Task 9: Final Verification

- [x] **Step 1: Full test suite**

```bash
uv run pytest --tb=short -q
```

Expected: all existing tests pass + new 015 tests pass. No regressions.

- [x] **Step 2: Static analysis**

```bash
uv run ruff check .
uv run mypy src/hks
```

- [x] **Step 3: Behavioral verification**

Run a manual query to verify the new fields appear:

```bash
cd /tmp && mkdir -p test-015 && echo "Project Atlas is a key initiative." > test-015/atlas.txt
KS_ROOT=/tmp/test-015-ks uv run ks ingest /tmp/test-015/atlas.txt
KS_ROOT=/tmp/test-015-ks uv run ks query "What is Project Atlas?" --writeback=no | python3 -m json.tool
```

Verify:
- `retrieval_score` present
- `calibrated_confidence` present
- `writeback_eligible` present (likely `false` for wiki route)
- `confidence` unchanged from before
- A `rerank` trace step is present

```bash
KS_ROOT=/tmp/test-015-ks uv run ks query "What is Project Atlas?" --writeback=yes | python3 -m json.tool
```

Verify:
- Writeback trace step has `"forced": true`
- Status is `"forced-committed"`

- [x] **Step 4: Contract backward compatibility**

```bash
uv run pytest tests/contract/ -v
```

All contract tests (including phase 1 preservation) must pass.

---

## Risk Notes

1. **Backward compatibility**: `confidence` field value is never changed. New fields are additive-only. `decide()` retains `confidence` kwarg for any caller not yet migrated to `assessment`.

2. **Wiki writeback behavioral change**: After 015, `--writeback=auto` with a wiki route winner will **never** auto-commit (wiki is always ineligible). This is intentional per the design spec. Tests that previously expected `auto-committed` for wiki hits need updating.

3. **`flag="yes"` status change**: `"committed"` → `"forced-committed"`. Any external tooling or agent that checks `status == "committed"` needs awareness. The `"committed"` status string is still used by `ask` + user confirms.

4. **Rerank trace step is additive**: The existing `merge` step is preserved. A new `rerank` step is added before it. No existing trace step is removed.

5. **Graph writeback near-zero in practice**: Graph extraction currently produces limited `evidence_by_relpath`. Per spec, this is intentional anti-pollution, not a bug.
