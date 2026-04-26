"""Data models for 008 LLM extraction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

type ExtractionMode = Literal["preview", "store"]
type ProviderCredentialStatus = Literal["not_required", "present", "missing"]
type ValidationStatus = Literal["valid", "invalid"]
type ArtifactStatus = Literal["valid", "invalid", "partial"]
type EntityType = Literal["Person", "Project", "Document", "Event", "Concept"]
type RelationType = Literal["owns", "depends_on", "impacts", "references", "belongs_to"]
type FindingSeverity = Literal["error", "warning", "info"]

ENTITY_TYPES: frozenset[str] = frozenset(("Person", "Project", "Document", "Event", "Concept"))
RELATION_TYPES: frozenset[str] = frozenset(
    ("owns", "depends_on", "impacts", "references", "belongs_to")
)
SCHEMA_VERSION = 1
DEFAULT_PROMPT_VERSION = "llm-extraction-v1"
DEFAULT_FAKE_MODEL = "fake-llm-extractor-v1"


@dataclass(frozen=True, slots=True)
class LlmProviderConfig:
    provider_id: str
    model_id: str
    endpoint: str | None = None
    network_opt_in: bool = False
    timeout_seconds: int = 30
    credential_status: ProviderCredentialStatus = "not_required"


@dataclass(frozen=True, slots=True)
class LlmExtractionRequest:
    source_relpath: str
    mode: ExtractionMode = "preview"
    prompt_version: str = DEFAULT_PROMPT_VERSION
    provider: LlmProviderConfig = field(
        default_factory=lambda: LlmProviderConfig(
            provider_id="fake",
            model_id=DEFAULT_FAKE_MODEL,
        )
    )
    force_new_run: bool = False
    requested_by: str | None = None

    def idempotency_key(self, *, source_fingerprint: str, parser_fingerprint: str) -> str:
        payload = {
            "source_relpath": self.source_relpath,
            "source_fingerprint": source_fingerprint,
            "parser_fingerprint": parser_fingerprint,
            "prompt_version": self.prompt_version,
            "provider_id": self.provider.provider_id,
            "model_id": self.provider.model_id,
            "schema_version": SCHEMA_VERSION,
        }
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_artifact_dict(self) -> dict[str, Any]:
        return {
            "source_relpath": self.source_relpath,
            "mode": "store",
            "prompt_version": self.prompt_version,
            "provider_id": self.provider.provider_id,
            "model_id": self.provider.model_id,
            "force_new_run": self.force_new_run,
            "requested_by": self.requested_by,
        }


@dataclass(frozen=True, slots=True)
class Evidence:
    source_relpath: str
    quote: str
    chunk_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_relpath": self.source_relpath,
            "chunk_id": self.chunk_id,
            "quote": self.quote,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }


@dataclass(frozen=True, slots=True)
class ClassificationLabel:
    label: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class KeyFact:
    fact: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact": self.fact,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    candidate_id: str
    type: EntityType
    label: str
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "type": self.type,
            "label": self.label,
            "aliases": self.aliases,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class RelationCandidate:
    candidate_id: str
    type: RelationType
    source_candidate_id: str
    target_candidate_id: str
    confidence: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "type": self.type,
            "source_candidate_id": self.source_candidate_id,
            "target_candidate_id": self.target_candidate_id,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class LlmFinding:
    severity: FindingSeverity
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    source_relpath: str
    source_fingerprint: str
    parser_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_relpath": self.source_relpath,
            "source_fingerprint": self.source_fingerprint,
            "parser_fingerprint": self.parser_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider_id: str
    model_id: str
    prompt_version: str
    generated_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True, slots=True)
class LlmExtractionResult:
    operation: Literal["llm_classify"]
    mode: ExtractionMode
    source: SourceProvenance
    provider: ProviderMetadata
    classification: list[ClassificationLabel]
    summary_candidate: str | None
    key_facts: list[KeyFact]
    entity_candidates: list[EntityCandidate]
    relation_candidates: list[RelationCandidate]
    confidence: float
    artifact: dict[str, Any] | None = None
    findings: list[LlmFinding] = field(default_factory=list)

    def to_detail(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "mode": self.mode,
            "source": self.source.to_dict(),
            "provider": self.provider.to_dict(),
            "classification": [item.to_dict() for item in self.classification],
            "summary_candidate": self.summary_candidate,
            "key_facts": [item.to_dict() for item in self.key_facts],
            "entity_candidates": [item.to_dict() for item in self.entity_candidates],
            "relation_candidates": [item.to_dict() for item in self.relation_candidates],
            "confidence": self.confidence,
            "artifact": self.artifact,
            "findings": [item.to_dict() for item in self.findings],
        }

    def with_artifact(self, artifact: dict[str, Any]) -> LlmExtractionResult:
        return LlmExtractionResult(
            operation=self.operation,
            mode=self.mode,
            source=self.source,
            provider=self.provider,
            classification=self.classification,
            summary_candidate=self.summary_candidate,
            key_facts=self.key_facts,
            entity_candidates=self.entity_candidates,
            relation_candidates=self.relation_candidates,
            confidence=self.confidence,
            artifact=artifact,
            findings=self.findings,
        )


@dataclass(frozen=True, slots=True)
class ExtractionArtifact:
    artifact_id: str
    schema_version: int
    idempotency_key: str
    created_at: str
    status: ArtifactStatus
    request: LlmExtractionRequest
    result: LlmExtractionResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "status": self.status,
            "request": self.request.to_artifact_dict(),
            "result": self.result.to_detail(),
        }
