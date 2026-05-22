"""Route-specific confidence assessment and writeback eligibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hks.core.schema import Route

_AUTO_THRESHOLDS: dict[Route, float] = {
    "wiki": 999.0,
    "graph": 0.75,
    "vector": 0.65,
    "page_tree": 0.50,
}


@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    """Route-specific confidence and auto-writeback eligibility."""

    retrieval_score: float
    calibrated_confidence: float
    writeback_eligible: bool
    auto_threshold: float = 0.75
    reasons: list[str] = field(default_factory=list)


def assess(
    *,
    route: Route,
    raw_score: float,
    evidence: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> ConfidenceAssessment:
    """Assess confidence and route-specific auto-writeback eligibility."""

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

    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=False,
        auto_threshold=999.0,
        reasons=[f"unknown route: {route}"],
    )


def _assess_wiki(retrieval_score: float, calibrated: float) -> ConfidenceAssessment:
    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=False,
        auto_threshold=_AUTO_THRESHOLDS["wiki"],
        reasons=["wiki route: auto writeback ineligible (use --writeback=yes)"],
    )


def _assess_graph(
    retrieval_score: float,
    calibrated: float,
    evidence: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> ConfidenceAssessment:
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
    elif not any(_has_nonempty_str(item, "source_relpath") for item in evidence):
        eligible = False
        reasons.append("graph evidence missing source_relpath")

    if eligible:
        reasons.append("graph route: all evidence requirements met")

    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=eligible,
        auto_threshold=_AUTO_THRESHOLDS["graph"],
        reasons=reasons,
    )


def _assess_vector(
    retrieval_score: float,
    calibrated: float,
    evidence: list[dict[str, Any]],
) -> ConfidenceAssessment:
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
        if not _has_nonempty_str(first, "source_relpath"):
            eligible = False
            reasons.append("vector evidence missing source_relpath")
        if not _has_nonempty_str(first, "quote"):
            eligible = False
            reasons.append("vector evidence missing quote")

    if eligible:
        reasons.append("vector route: all evidence requirements met")

    return ConfidenceAssessment(
        retrieval_score=retrieval_score,
        calibrated_confidence=calibrated,
        writeback_eligible=eligible,
        auto_threshold=_AUTO_THRESHOLDS["vector"],
        reasons=reasons,
    )


def _assess_page_tree(
    retrieval_score: float,
    calibrated: float,
    evidence: list[dict[str, Any]],
) -> ConfidenceAssessment:
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
        if not _has_nonempty_str(first, "source_relpath"):
            eligible = False
            reasons.append("page_tree evidence missing source_relpath")
        if not _has_nonempty_str(first, "quote"):
            eligible = False
            reasons.append("page_tree evidence missing non-empty quote")
        if not _has_nonempty_str(first, "section_path"):
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
        auto_threshold=_AUTO_THRESHOLDS["page_tree"],
        reasons=reasons,
    )


def _has_nonempty_str(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, str) and bool(value)
