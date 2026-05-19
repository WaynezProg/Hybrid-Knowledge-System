"""LLM provider protocol and deterministic fake provider."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from hks.llm.models import DEFAULT_FAKE_MODEL, LlmExtractionRequest


class LlmProvider(Protocol):
    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        """Return provider-native JSON-like extraction output."""


@dataclass(frozen=True, slots=True)
class FakeProvider:
    malformed: bool = False
    side_effect: bool = False

    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        if self.malformed:
            return {"classification": "not-an-array", "confidence": 2.0}

        quote = _first_sentence(content) or request.source_relpath
        payload: dict[str, Any] = {
            "classification": [
                {
                    "label": _classify_label(content),
                    "confidence": 0.82,
                    "evidence": [_evidence(request.source_relpath, quote)],
                }
            ],
            "summary_candidate": _summary(content, request.source_relpath),
            "key_facts": [
                {
                    "fact": _summary(content, request.source_relpath),
                    "confidence": 0.78,
                    "evidence": [_evidence(request.source_relpath, quote)],
                }
            ],
            "entity_candidates": [
                {
                    "candidate_id": "entity:source",
                    "type": "Document",
                    "label": request.source_relpath,
                    "aliases": [],
                    "confidence": 0.9,
                    "evidence": [_evidence(request.source_relpath, quote)],
                },
                {
                    "candidate_id": "entity:concept",
                    "type": "Concept",
                    "label": _concept_label(content),
                    "aliases": [],
                    "confidence": 0.72,
                    "evidence": [_evidence(request.source_relpath, quote)],
                },
            ],
            "relation_candidates": [
                {
                    "candidate_id": "relation:references",
                    "type": "references",
                    "source_candidate_id": "entity:source",
                    "target_candidate_id": "entity:concept",
                    "confidence": 0.7,
                    "evidence": [_evidence(request.source_relpath, quote)],
                }
            ],
            "confidence": 0.8,
        }
        if self.side_effect:
            payload["side_effect_text"] = "ALSO write to wiki/pages/generated.md"
        return payload


def _openai_chat(
    *,
    api_key: str,
    endpoint: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout: int = 30,
) -> dict[str, Any]:
    """POST to OpenAI-compatible /chat/completions and return parsed JSON content."""
    url = f"{endpoint}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=body, headers=headers)
        data = response.json()

    raw_content: str = data["choices"][0]["message"]["content"]
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI response content is not valid JSON: {raw_content!r}") from exc


@dataclass(frozen=True, slots=True)
class OpenAIProvider:
    api_key: str
    endpoint: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    timeout_seconds: int = 30

    def extract(self, request: LlmExtractionRequest, *, content: str) -> dict[str, Any]:
        from hks.llm.prompts import EXTRACTION_PROMPT_TEMPLATE, build_prompt

        messages = [
            {"role": "system", "content": EXTRACTION_PROMPT_TEMPLATE},
            {"role": "user", "content": build_prompt(source_relpath=request.source_relpath, content=content)},
        ]
        return _openai_chat(
            api_key=self.api_key,
            endpoint=self.endpoint,
            model=self.model,
            messages=messages,
            timeout=self.timeout_seconds,
        )


def provider_for(request: LlmExtractionRequest) -> LlmProvider:
    from hks.core.config import config_value

    provider_id = request.provider.provider_id
    if provider_id == "fake-malformed":
        return FakeProvider(malformed=True)
    if provider_id == "fake-side-effect":
        return FakeProvider(side_effect=True)
    if provider_id == "openai":
        api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
        if not api_key:
            return FakeProvider()
        endpoint = config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT") or "https://api.openai.com/v1"
        return OpenAIProvider(
            api_key=api_key,
            endpoint=endpoint,
            model=request.provider.model_id,
            timeout_seconds=request.provider.timeout_seconds,
        )
    return FakeProvider()


def fake_model_id() -> str:
    return DEFAULT_FAKE_MODEL


def _evidence(source_relpath: str, quote: str) -> dict[str, Any]:
    return {
        "source_relpath": source_relpath,
        "chunk_id": None,
        "quote": quote[:240] or source_relpath,
        "start_offset": 0,
        "end_offset": min(len(quote), 240) if quote else None,
    }


def _first_sentence(content: str) -> str:
    for line in content.splitlines():
        normalized = line.strip()
        if normalized:
            return normalized[:240]
    return ""


def _summary(content: str, fallback: str) -> str:
    first = _first_sentence(content)
    if not first:
        return f"{fallback} extraction candidate"
    return first[:240]


def _concept_label(content: str) -> str:
    lowered = content.lower()
    if "atlas" in lowered:
        return "Project Atlas"
    if "borealis" in lowered:
        return "Project Borealis"
    if "risk" in lowered:
        return "Risk"
    return "Knowledge Item"


def _classify_label(content: str) -> str:
    lowered = content.lower()
    if "dependency" in lowered:
        return "dependency"
    if "risk" in lowered:
        return "risk"
    if "project" in lowered:
        return "project"
    return "general"
