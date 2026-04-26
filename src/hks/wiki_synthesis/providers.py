"""Deterministic fake wiki synthesizer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from hks.llm.models import LlmFinding
from hks.storage.wiki import WikiStore
from hks.wiki_synthesis.models import WikiSynthesisCandidate, WikiSynthesisRequest


class WikiSynthesizer(Protocol):
    def synthesize(
        self,
        request: WikiSynthesisRequest,
        *,
        extraction_artifact_id: str,
        extraction_result: dict[str, Any],
    ) -> WikiSynthesisCandidate:
        """Return a schema-valid wiki candidate from an 008 artifact."""


@dataclass(frozen=True, slots=True)
class FakeWikiSynthesizer:
    side_effect: bool = False

    def synthesize(
        self,
        request: WikiSynthesisRequest,
        *,
        extraction_artifact_id: str,
        extraction_result: dict[str, Any],
    ) -> WikiSynthesisCandidate:
        source = extraction_result["source"]
        title = _title(extraction_result)
        target_slug = request.target_slug or WikiStore().slug_base(title)
        summary = str(extraction_result.get("summary_candidate") or title)
        body = _body(title, summary, extraction_result)
        findings: list[LlmFinding] = []
        if self.side_effect:
            findings.append(
                LlmFinding(
                    severity="warning",
                    code="side_effect_text_ignored",
                    message="provider side-effect text was ignored",
                )
            )
        return WikiSynthesisCandidate(
            candidate_id=f"candidate:{extraction_artifact_id}:{target_slug}",
            target_slug=target_slug,
            title=title,
            summary=summary[:240],
            body=body,
            source_relpath=str(source["source_relpath"]),
            extraction_artifact_id=extraction_artifact_id,
            source_fingerprint=str(source["source_fingerprint"]),
            parser_fingerprint=str(source["parser_fingerprint"]),
            prompt_version=request.prompt_version,
            provider_id=request.provider.provider_id,
            model_id=request.provider.model_id,
            confidence=float(extraction_result.get("confidence", 0.0)),
            diff_summary=f"create-or-update pages/{target_slug}.md",
            findings=findings,
        )


def provider_for(request: WikiSynthesisRequest) -> WikiSynthesizer:
    return FakeWikiSynthesizer(side_effect=request.provider.provider_id == "fake-side-effect")


def _title(result: dict[str, Any]) -> str:
    entities = result.get("entity_candidates")
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict) and entity.get("label"):
                label = str(entity["label"]).strip()
                if label and not label.endswith(".txt") and not label.endswith(".md"):
                    return label
    source = result.get("source", {})
    if isinstance(source, dict):
        return str(source.get("source_relpath", "wiki-synthesis")).rsplit(".", 1)[0]
    return "wiki-synthesis"


def _body(title: str, summary: str, result: dict[str, Any]) -> str:
    facts = result.get("key_facts")
    fact_lines: list[str] = []
    if isinstance(facts, list):
        for fact in facts[:8]:
            if isinstance(fact, dict) and fact.get("fact"):
                fact_lines.append(f"- {str(fact['fact']).strip()}")
    if not fact_lines:
        fact_lines.append(f"- {summary}")
    return "\n".join([f"# {title}", "", summary, "", "## Key Facts", *fact_lines]).strip()
