"""LLM-backed reranking with deterministic fallback."""

from __future__ import annotations

import json

import httpx

from hks.core.config import config_value
from hks.llm.config import hosted_provider_ready
from hks.llm.providers import _openai_chat
from hks.rerank.rrf import rrf_rerank
from hks.retrieval.models import Candidate


def llm_rerank(
    question: str,
    candidates: list[Candidate],
) -> tuple[list[Candidate], dict[str, object]]:
    if not hosted_provider_ready("openai"):
        return rrf_rerank(candidates), {
            "strategy": "rrf",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": "provider_not_ready",
        }
    api_key = config_value("HKS_LLM_PROVIDER_OPENAI_API_KEY") or config_value("OPENAI_API_KEY")
    if not api_key:
        return rrf_rerank(candidates), {
            "strategy": "rrf",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": "credential_missing",
        }
    endpoint = config_value("HKS_LLM_PROVIDER_OPENAI_ENDPOINT") or "https://api.openai.com/v1"
    model = config_value("HKS_LLM_MODEL") or "gpt-4o-mini"

    capped = candidates[:10]
    snippet_list = "\n".join(
        f"[{i}] ({c.source_route}) {c.text[:200]}" for i, c in enumerate(capped)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a relevance ranker. Given a question and numbered text snippets, "
                "return a JSON object with a 'ranking' key containing an array of snippet "
                "indices sorted by relevance (most relevant first). "
                'Example: {"ranking": [2, 0, 1]}'
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nSnippets:\n{snippet_list}",
        },
    ]

    try:
        result = _openai_chat(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            messages=messages,
            timeout=30,
        )
        if not isinstance(result, dict):
            raise ValueError("rerank response is not an object")
        ranking = result.get("ranking", [])
        if not isinstance(ranking, list):
            raise TypeError("rerank response missing ranking list")

        ranked: list[Candidate] = []
        seen: set[int] = set()
        for idx in ranking:
            if isinstance(idx, int) and 0 <= idx < len(capped) and idx not in seen:
                seen.add(idx)
                ranked.append(
                    Candidate(
                        text=capped[idx].text,
                        source_route=capped[idx].source_route,
                        score=capped[idx].score,
                        metadata=capped[idx].metadata,
                    )
                )
        for i, c in enumerate(capped):
            if i not in seen:
                ranked.append(c)
        return ranked, {"strategy": "llm", "status": "success"}
    except Exception as exc:
        return rrf_rerank(candidates), {
            "strategy": "llm",
            "status": "fallback",
            "fallback_strategy": "rrf",
            "reason": classify_rerank_error(exc),
        }


def classify_rerank_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "openai_timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "openai_http_error"
    if isinstance(exc, json.JSONDecodeError):
        return "openai_invalid_json"
    if isinstance(exc, (KeyError, IndexError, TypeError, ValueError)):
        return "openai_invalid_ranking"
    return "unexpected_error"


def rerank_candidates(
    question: str,
    candidates: list[Candidate],
) -> tuple[list[Candidate], str, dict[str, object]]:
    if hosted_provider_ready("openai"):
        ranked, detail = llm_rerank(question, candidates)
        return ranked, "llm-rerank", detail
    ranked = rrf_rerank(candidates)
    return ranked, "rrf", {"strategy": "rrf", "status": "primary"}
