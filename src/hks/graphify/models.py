"""Data models for 010 Graphify derived artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from hks.llm.models import LlmProviderConfig

type GraphifyMode = Literal["preview", "store"]
type GraphifyRunStatus = Literal["valid", "invalid", "partial"]
type GraphifyNodeKind = Literal["source", "wiki_page", "entity", "concept", "artifact", "community"]
type GraphifySourceLayer = Literal["wiki", "graph", "llm_extraction", "llm_wiki", "graphify"]
type GraphifyEvidence = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]
type GraphifyFindingSeverity = Literal["info", "warning", "error"]
type ClassificationMethod = Literal["deterministic", "llm"]

SCHEMA_VERSION = 1
DEFAULT_ALGORITHM_VERSION = "graphify-v1"
DEFAULT_FAKE_MODEL = "fake-graphify-classifier-v1"


@dataclass(frozen=True, slots=True)
class GraphifyRequest:
    mode: GraphifyMode = "preview"
    provider: LlmProviderConfig = field(
        default_factory=lambda: LlmProviderConfig(
            provider_id="fake",
            model_id=DEFAULT_FAKE_MODEL,
        )
    )
    algorithm_version: str = DEFAULT_ALGORITHM_VERSION
    include_html: bool = True
    include_report: bool = True
    force_new_run: bool = False
    requested_by: str | None = None

    def idempotency_key(self, *, input_fingerprint: str, created_at_iso: str | None = None) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "input_fingerprint": input_fingerprint,
            "algorithm_version": self.algorithm_version,
            "provider_id": self.provider.provider_id,
            "model_id": self.provider.model_id,
            "include_html": self.include_html,
            "include_report": self.include_report,
        }
        if self.force_new_run:
            payload["created_at_iso"] = created_at_iso or ""
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_artifact_dict(self) -> dict[str, Any]:
        return {
            "mode": "store",
            "provider_id": self.provider.provider_id,
            "model_id": self.provider.model_id,
            "include_html": self.include_html,
            "include_report": self.include_report,
            "force_new_run": self.force_new_run,
            "requested_by": self.requested_by,
        }


@dataclass(frozen=True, slots=True)
class GraphifyProvenance:
    source_relpath: str | None = None
    wiki_page: str | None = None
    artifact_id: str | None = None
    source_fingerprint: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_relpath": self.source_relpath,
            "wiki_page": self.wiki_page,
            "artifact_id": self.artifact_id,
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class GraphifyNode:
    id: str
    label: str
    kind: GraphifyNodeKind
    source_layer: GraphifySourceLayer
    source_ref: str
    provenance: GraphifyProvenance = field(default_factory=GraphifyProvenance)
    community_id: str | None = None

    def with_community(self, community_id: str) -> GraphifyNode:
        return replace(self, community_id=community_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "source_layer": self.source_layer,
            "source_ref": self.source_ref,
            "provenance": self.provenance.to_dict(),
            "community_id": self.community_id,
        }


@dataclass(frozen=True, slots=True)
class GraphifyEdge:
    id: str
    source: str
    target: str
    relation: str
    evidence: GraphifyEvidence
    confidence_score: float
    weight: float
    source_layer: GraphifySourceLayer
    source_ref: str
    rationale: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "evidence": self.evidence,
            "confidence_score": self.confidence_score,
            "weight": self.weight,
            "source_layer": self.source_layer,
            "source_ref": self.source_ref,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class GraphifyCommunity:
    community_id: str
    label: str
    summary: str
    node_ids: list[str]
    representative_edge_ids: list[str]
    classification_method: ClassificationMethod
    confidence_score: float
    provenance: GraphifyProvenance = field(default_factory=GraphifyProvenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "community_id": self.community_id,
            "label": self.label,
            "summary": self.summary,
            "node_ids": self.node_ids,
            "representative_edge_ids": self.representative_edge_ids,
            "classification_method": self.classification_method,
            "confidence_score": self.confidence_score,
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GraphifyAuditFinding:
    severity: GraphifyFindingSeverity
    code: str
    message: str
    source_ref: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source_ref": self.source_ref,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class GraphifyGraph:
    generated_at: str
    input_layers: list[Literal["wiki", "graph", "llm_extraction", "llm_wiki"]]
    nodes: list[GraphifyNode]
    edges: list[GraphifyEdge]
    communities: list[GraphifyCommunity]
    audit_findings: list[GraphifyAuditFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": self.generated_at,
            "input_layers": self.input_layers,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "communities": [community.to_dict() for community in self.communities],
            "audit_findings": [finding.to_dict() for finding in self.audit_findings],
        }


@dataclass(frozen=True, slots=True)
class GraphifyRun:
    run_id: str
    created_at: str
    status: GraphifyRunStatus
    idempotency_key: str
    input_fingerprint: str
    algorithm_version: str
    request: GraphifyRequest
    artifacts: dict[str, str | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "schema_version": SCHEMA_VERSION,
            "created_at": self.created_at,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "input_fingerprint": self.input_fingerprint,
            "algorithm_version": self.algorithm_version,
            "request": self.request.to_artifact_dict(),
            "artifacts": self.artifacts,
        }


@dataclass(frozen=True, slots=True)
class GraphifyResult:
    mode: GraphifyMode
    graph: GraphifyGraph
    input_fingerprint: str
    source: list[Literal["wiki", "graph", "vector"]]
    artifacts: dict[str, Any]
    idempotent_reuse: bool = False
    confidence: float = 1.0

    def to_detail(self) -> dict[str, Any]:
        counts = {"info": 0, "warning": 0, "error": 0}
        for finding in self.graph.audit_findings:
            counts[finding.severity] += 1
        return {
            "operation": "graphify_build",
            "mode": self.mode,
            "input_fingerprint": self.input_fingerprint,
            "node_count": len(self.graph.nodes),
            "edge_count": len(self.graph.edges),
            "community_count": len(self.graph.communities),
            "audit_summary": counts,
            "artifacts": self.artifacts,
            "idempotent_reuse": self.idempotent_reuse,
            "confidence": self.confidence,
        }
