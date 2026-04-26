"""Data models for 011 watch orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from hks.core.manifest import SourceFormat

type WatchMode = Literal["dry-run", "execute"]
type WatchProfile = Literal["scan-only", "ingest-only", "derived-refresh", "wiki-apply", "full"]
type WatchOperation = Literal["scan", "run", "status"]
type WatchSourceState = Literal["unchanged", "stale", "new", "missing", "unsupported", "corrupt"]
type WatchRootKind = Literal["external", "raw_sources"]
type RefreshActionKind = Literal[
    "ingest",
    "prune",
    "llm_classify",
    "wiki_synthesize",
    "wiki_apply",
    "graphify_build",
    "report_issue",
]
type RefreshActionStatus = Literal["planned", "skipped", "running", "completed", "failed"]
type WatchRunStatus = Literal["planned", "running", "completed", "failed", "partial"]
type IssueSeverity = Literal["info", "warning", "error"]

SOURCE_STATES: tuple[WatchSourceState, ...] = (
    "unchanged",
    "stale",
    "new",
    "missing",
    "unsupported",
    "corrupt",
)
ACTION_STATUSES: tuple[RefreshActionStatus, ...] = (
    "planned",
    "skipped",
    "running",
    "completed",
    "failed",
)
ARTIFACT_COUNT_KEYS: tuple[str, ...] = (
    "llm_extraction_stale",
    "wiki_candidate_stale",
    "graphify_stale",
    "orphaned",
)


def stable_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WatchRequest:
    operation: WatchOperation
    mode: WatchMode = "dry-run"
    profile: WatchProfile = "scan-only"
    source_roots: list[Path] = field(default_factory=list)
    prune: bool = False
    include_llm: bool = False
    include_wiki_apply: bool = False
    include_graphify: bool = False
    force: bool = False
    requested_by: str | None = None


@dataclass(frozen=True, slots=True)
class WatchRoot:
    root_path: str
    kind: WatchRootKind
    created_at: str
    last_seen_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_path": self.root_path,
            "kind": self.kind,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
        }


@dataclass(frozen=True, slots=True)
class WatchIssue:
    severity: IssueSeverity
    code: str
    message: str
    source_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class WatchSource:
    relpath: str
    state: WatchSourceState
    format: SourceFormat | None = None
    current_sha256: str | None = None
    manifest_sha256: str | None = None
    current_parser_fingerprint: str | None = None
    manifest_parser_fingerprint: str | None = None
    size_bytes: int | None = None
    root_path: str | None = None
    path: str | None = None
    lineage_refs: list[str] = field(default_factory=list)
    issues: list[WatchIssue] = field(default_factory=list)

    def observation(self) -> dict[str, Any]:
        return {
            "relpath": self.relpath,
            "state": self.state,
            "format": self.format,
            "current_sha256": self.current_sha256,
            "manifest_sha256": self.manifest_sha256,
            "current_parser_fingerprint": self.current_parser_fingerprint,
            "manifest_parser_fingerprint": self.manifest_parser_fingerprint,
            "lineage_refs": sorted(self.lineage_refs),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class RefreshAction:
    action_id: str
    kind: RefreshActionKind
    source_relpath: str | None
    depends_on: list[str] = field(default_factory=list)
    status: RefreshActionStatus = "planned"
    input_fingerprint: str | None = None
    output_refs: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None

    def with_status(
        self,
        status: RefreshActionStatus,
        *,
        output_refs: list[str] | None = None,
        error: dict[str, Any] | None = None,
    ) -> RefreshAction:
        return replace(
            self,
            status=status,
            output_refs=list(output_refs if output_refs is not None else self.output_refs),
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "source_relpath": self.source_relpath,
            "depends_on": self.depends_on,
            "status": self.status,
            "input_fingerprint": self.input_fingerprint,
            "output_refs": self.output_refs,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RefreshAction:
        return cls(
            action_id=str(payload["action_id"]),
            kind=payload["kind"],
            source_relpath=payload.get("source_relpath"),
            depends_on=list(payload.get("depends_on", [])),
            status=payload.get("status", "planned"),
            input_fingerprint=payload.get("input_fingerprint"),
            output_refs=list(payload.get("output_refs", [])),
            error=payload.get("error"),
        )


@dataclass(frozen=True, slots=True)
class RefreshPlan:
    plan_id: str
    created_at: str
    plan_fingerprint: str
    mode: WatchMode
    profile: WatchProfile
    source_counts: dict[str, int]
    artifact_counts: dict[str, int]
    actions: list[RefreshAction]
    issues: list[WatchIssue] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "plan_fingerprint": self.plan_fingerprint,
            "mode": self.mode,
            "profile": self.profile,
            "source_counts": self.source_counts,
            "artifact_counts": self.artifact_counts,
            "actions": [action.to_dict() for action in self.actions],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RefreshPlan:
        return cls(
            plan_id=str(payload["plan_id"]),
            created_at=str(payload["created_at"]),
            plan_fingerprint=str(payload["plan_fingerprint"]),
            mode=payload["mode"],
            profile=payload["profile"],
            source_counts=dict(payload["source_counts"]),
            artifact_counts=dict(payload["artifact_counts"]),
            actions=[RefreshAction.from_dict(item) for item in payload.get("actions", [])],
            issues=[
                WatchIssue(
                    severity=item["severity"],
                    code=str(item["code"]),
                    message=str(item["message"]),
                    source_ref=item.get("source_ref"),
                )
                for item in payload.get("issues", [])
            ],
            schema_version=str(payload.get("schema_version", "1.0")),
        )


@dataclass(frozen=True, slots=True)
class WatchSummaryDetail:
    operation: WatchOperation
    mode: WatchMode
    profile: WatchProfile
    source_counts: dict[str, int]
    action_counts: dict[str, int]
    artifacts: dict[str, str | None]
    plan_id: str | None = None
    run_id: str | None = None
    plan_fingerprint: str | None = None
    idempotent_reuse: bool = False
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "watch_summary",
            "operation": self.operation,
            "mode": self.mode,
            "profile": self.profile,
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "plan_fingerprint": self.plan_fingerprint,
            "source_counts": self.source_counts,
            "action_counts": self.action_counts,
            "artifacts": self.artifacts,
            "idempotent_reuse": self.idempotent_reuse,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class WatchRun:
    run_id: str
    created_at: str
    completed_at: str | None
    status: WatchRunStatus
    plan_id: str
    plan_fingerprint: str
    mode: WatchMode
    profile: WatchProfile
    requested_by: str | None
    actions: list[RefreshAction]
    summary: WatchSummaryDetail
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "plan_id": self.plan_id,
            "plan_fingerprint": self.plan_fingerprint,
            "mode": self.mode,
            "profile": self.profile,
            "requested_by": self.requested_by,
            "actions": [action.to_dict() for action in self.actions],
            "summary": self.summary.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WatchRun:
        summary_payload = dict(payload["summary"])
        summary = WatchSummaryDetail(
            operation=summary_payload["operation"],
            mode=summary_payload["mode"],
            profile=summary_payload["profile"],
            plan_id=summary_payload.get("plan_id"),
            run_id=summary_payload.get("run_id"),
            plan_fingerprint=summary_payload.get("plan_fingerprint"),
            source_counts=dict(summary_payload["source_counts"]),
            action_counts=dict(summary_payload["action_counts"]),
            artifacts=dict(summary_payload["artifacts"]),
            idempotent_reuse=bool(summary_payload.get("idempotent_reuse", False)),
            confidence=float(summary_payload.get("confidence", 1.0)),
        )
        return cls(
            run_id=str(payload["run_id"]),
            created_at=str(payload["created_at"]),
            completed_at=payload.get("completed_at"),
            status=payload["status"],
            plan_id=str(payload["plan_id"]),
            plan_fingerprint=str(payload["plan_fingerprint"]),
            mode=payload["mode"],
            profile=payload["profile"],
            requested_by=payload.get("requested_by"),
            actions=[RefreshAction.from_dict(item) for item in payload.get("actions", [])],
            summary=summary,
            schema_version=str(payload.get("schema_version", "1.0")),
        )


def zero_source_counts() -> dict[str, int]:
    return {state: 0 for state in SOURCE_STATES}


def zero_action_counts() -> dict[str, int]:
    return {status: 0 for status in ACTION_STATUSES}


def zero_artifact_counts() -> dict[str, int]:
    return {key: 0 for key in ARTIFACT_COUNT_KEYS}
