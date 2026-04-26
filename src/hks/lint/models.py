"""Data models for runtime consistency linting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from hks.core.manifest import ManifestEntry
from hks.graph.store import GraphPayload
from hks.storage.wiki import WikiPage

type Severity = Literal["error", "warning", "info"]
type FindingCategory = Literal[
    "orphan_page",
    "dead_link",
    "duplicate_slug",
    "manifest_wiki_mismatch",
    "wiki_source_mismatch",
    "dangling_manifest_entry",
    "orphan_raw_source",
    "manifest_vector_mismatch",
    "orphan_vector_chunk",
    "graph_drift",
    "fingerprint_drift",
    "llm_artifact_invalid",
    "llm_artifact_corrupt",
    "wiki_candidate_artifact_invalid",
    "wiki_candidate_artifact_corrupt",
    "wiki_synthesis_frontmatter_invalid",
    "wiki_synthesis_partial_apply",
]
type FixActionKind = Literal[
    "rebuild_index",
    "prune_orphan_vector_chunks",
    "prune_orphan_graph_nodes",
    "prune_orphan_graph_edges",
]
type FixOutcome = Literal["planned", "success", "apply_failed"]
type FixSkipReason = Literal[
    "requires_manual",
    "unsupported_in_005",
    "manifest_truth_unknown",
    "apply_failed",
]
type FixMode = Literal["none", "plan", "apply"]
type SeverityThreshold = Literal["error", "warning", "info"]

FINDING_SEVERITY: dict[FindingCategory, Severity] = {
    "orphan_page": "warning",
    "dead_link": "warning",
    "duplicate_slug": "warning",
    "manifest_wiki_mismatch": "error",
    "wiki_source_mismatch": "error",
    "dangling_manifest_entry": "error",
    "orphan_raw_source": "warning",
    "manifest_vector_mismatch": "error",
    "orphan_vector_chunk": "warning",
    "graph_drift": "error",
    "fingerprint_drift": "info",
    "llm_artifact_invalid": "error",
    "llm_artifact_corrupt": "error",
    "wiki_candidate_artifact_invalid": "error",
    "wiki_candidate_artifact_corrupt": "error",
    "wiki_synthesis_frontmatter_invalid": "error",
    "wiki_synthesis_partial_apply": "error",
}

SEVERITY_RANK: dict[Severity, int] = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True, slots=True)
class Finding:
    category: FindingCategory
    severity: Severity
    target: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        category: FindingCategory,
        target: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> Finding:
        return cls(
            category=category,
            severity=FINDING_SEVERITY[category],
            target=target,
            message=message,
            details=dict(details or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "category": self.category,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True, slots=True)
class FixAction:
    action: FixActionKind
    target: str
    outcome: FixOutcome
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "action": self.action,
            "target": self.target,
            "outcome": self.outcome,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True, slots=True)
class FixSkip:
    category: FindingCategory
    reason: FixSkipReason
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "category": self.category,
            "reason": self.reason,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True, slots=True)
class WikiPageRecord:
    file_slug: str
    page: WikiPage


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    manifest_entries: dict[str, ManifestEntry]
    raw_source_relpaths: set[str]
    wiki_pages: dict[str, WikiPageRecord]
    wiki_index_slugs: list[str]
    vector_ids: set[str]
    graph: GraphPayload
    llm_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    llm_artifact_errors: dict[str, str] = field(default_factory=dict)
    wiki_candidate_artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    wiki_candidate_artifact_errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LintResult:
    findings: list[Finding]
    fixes_planned: list[FixAction] = field(default_factory=list)
    fixes_applied: list[FixAction] = field(default_factory=list)
    fixes_skipped: list[FixSkip] = field(default_factory=list)

    def to_detail(self) -> dict[str, Any]:
        severity_counts: dict[Severity, int] = {"error": 0, "warning": 0, "info": 0}
        category_counts: dict[str, int] = {}
        for finding in self.findings:
            severity_counts[finding.severity] += 1
            category_counts[finding.category] = category_counts.get(finding.category, 0) + 1
        return {
            "findings": [finding.to_dict() for finding in self.findings],
            "severity_counts": severity_counts,
            "category_counts": category_counts,
            "fixes_planned": [action.to_dict() for action in self.fixes_planned],
            "fixes_applied": [action.to_dict() for action in self.fixes_applied],
            "fixes_skipped": [skip.to_dict() for skip in self.fixes_skipped],
        }
