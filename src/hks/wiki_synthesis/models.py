"""Data models for 009 wiki synthesis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from hks.llm.models import LlmFinding, LlmProviderConfig

type WikiSynthesisMode = Literal["preview", "store", "apply"]
type ApplyOperation = Literal["create", "update", "conflict", "already_applied"]
type ArtifactStatus = Literal["valid", "invalid", "partial"]

SCHEMA_VERSION = 1
DEFAULT_PROMPT_VERSION = "wiki-synthesis-v1"
DEFAULT_FAKE_MODEL = "fake-wiki-synthesizer-v1"


@dataclass(frozen=True, slots=True)
class WikiSynthesisRequest:
    mode: WikiSynthesisMode = "preview"
    source_relpath: str | None = None
    extraction_artifact_id: str | None = None
    candidate_artifact_id: str | None = None
    target_slug: str | None = None
    prompt_version: str = DEFAULT_PROMPT_VERSION
    provider: LlmProviderConfig = field(
        default_factory=lambda: LlmProviderConfig(
            provider_id="fake",
            model_id=DEFAULT_FAKE_MODEL,
        )
    )
    force_new_run: bool = False
    requested_by: str | None = None

    def idempotency_key(
        self,
        *,
        extraction_artifact_id: str,
        source_fingerprint: str,
        target_slug: str,
    ) -> str:
        payload = {
            "extraction_artifact_id": extraction_artifact_id,
            "source_fingerprint": source_fingerprint,
            "prompt_version": self.prompt_version,
            "provider_id": self.provider.provider_id,
            "model_id": self.provider.model_id,
            "target_slug": target_slug,
            "schema_version": SCHEMA_VERSION,
        }
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def to_artifact_dict(self) -> dict[str, Any]:
        return {
            "source_relpath": self.source_relpath,
            "extraction_artifact_id": self.extraction_artifact_id,
            "mode": "store",
            "target_slug": self.target_slug,
            "prompt_version": self.prompt_version,
            "provider_id": self.provider.provider_id,
            "model_id": self.provider.model_id,
            "force_new_run": self.force_new_run,
            "requested_by": self.requested_by,
        }


@dataclass(frozen=True, slots=True)
class WikiSynthesisCandidate:
    candidate_id: str
    target_slug: str
    title: str
    summary: str
    body: str
    source_relpath: str
    extraction_artifact_id: str
    source_fingerprint: str
    parser_fingerprint: str
    prompt_version: str
    provider_id: str
    model_id: str
    confidence: float
    diff_summary: str
    findings: list[LlmFinding] = field(default_factory=list)

    def lineage_tuple(self) -> tuple[str, str, str]:
        return (self.extraction_artifact_id, self.source_fingerprint, self.parser_fingerprint)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "schema_version": SCHEMA_VERSION,
            "target_slug": self.target_slug,
            "title": self.title,
            "summary": self.summary,
            "body": self.body,
            "source_relpath": self.source_relpath,
            "extraction_artifact_id": self.extraction_artifact_id,
            "source_fingerprint": self.source_fingerprint,
            "parser_fingerprint": self.parser_fingerprint,
            "prompt_version": self.prompt_version,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "confidence": self.confidence,
            "diff_summary": self.diff_summary,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WikiSynthesisCandidate:
        return cls(
            candidate_id=str(payload["candidate_id"]),
            target_slug=str(payload["target_slug"]),
            title=str(payload["title"]),
            summary=str(payload["summary"]),
            body=str(payload["body"]),
            source_relpath=str(payload["source_relpath"]),
            extraction_artifact_id=str(payload["extraction_artifact_id"]),
            source_fingerprint=str(payload["source_fingerprint"]),
            parser_fingerprint=str(payload["parser_fingerprint"]),
            prompt_version=str(payload["prompt_version"]),
            provider_id=str(payload["provider_id"]),
            model_id=str(payload["model_id"]),
            confidence=float(payload["confidence"]),
            diff_summary=str(payload["diff_summary"]),
            findings=[
                LlmFinding(
                    severity=str(item["severity"]),  # type: ignore[arg-type]
                    code=str(item["code"]),
                    message=str(item["message"]),
                )
                for item in payload.get("findings", [])
                if isinstance(item, dict)
            ],
        )


@dataclass(frozen=True, slots=True)
class WikiApplyResult:
    operation: ApplyOperation
    target_slug: str
    touched_pages: list[str]
    conflicts: list[LlmFinding]
    diff_summary: str
    idempotent_apply: bool = False
    log_entry_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "target_slug": self.target_slug,
            "touched_pages": self.touched_pages,
            "log_entry_id": self.log_entry_id,
            "conflicts": [finding.to_dict() for finding in self.conflicts],
            "diff_summary": self.diff_summary,
            "idempotent_apply": self.idempotent_apply,
        }


@dataclass(frozen=True, slots=True)
class WikiSynthesisArtifact:
    artifact_id: str
    schema_version: int
    idempotency_key: str
    created_at: str
    status: ArtifactStatus
    request: WikiSynthesisRequest
    candidate: WikiSynthesisCandidate

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "status": self.status,
            "request": self.request.to_artifact_dict(),
            "candidate": self.candidate.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class WikiSynthesisResult:
    mode: WikiSynthesisMode
    candidate: WikiSynthesisCandidate
    artifact: dict[str, Any] | None = None
    apply_result: WikiApplyResult | None = None
    findings: list[LlmFinding] = field(default_factory=list)

    def to_detail(self) -> dict[str, Any]:
        return {
            "operation": "wiki_synthesize",
            "mode": self.mode,
            "candidate": self.candidate.to_dict(),
            "artifact": self.artifact,
            "apply_result": self.apply_result.to_dict() if self.apply_result else None,
            "confidence": self.candidate.confidence,
            "findings": [finding.to_dict() for finding in self.findings],
        }

    def with_artifact(self, artifact: dict[str, Any]) -> WikiSynthesisResult:
        return WikiSynthesisResult(
            mode=self.mode,
            candidate=self.candidate,
            artifact=artifact,
            apply_result=self.apply_result,
            findings=self.findings,
        )

    def with_apply_result(self, apply_result: WikiApplyResult) -> WikiSynthesisResult:
        return WikiSynthesisResult(
            mode=self.mode,
            candidate=self.candidate,
            artifact=self.artifact,
            apply_result=apply_result,
            findings=self.findings,
        )
