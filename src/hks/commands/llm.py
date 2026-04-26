"""Command wrappers for 008 LLM extraction."""

from __future__ import annotations

from hks.adapters.contracts import validate_llm_summary
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.llm.config import build_request
from hks.llm.service import classify


def run_classify(
    *,
    source_relpath: str,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    prompt_version: str | None = None,
    force_new_run: bool = False,
    requested_by: str | None = None,
) -> QueryResponse:
    request = build_request(
        source_relpath=source_relpath,
        mode=mode,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        force_new_run=force_new_run,
        requested_by=requested_by,
    )
    result = classify(request)
    detail = result.to_detail()
    validate_llm_summary(detail)
    answer = (
        f"llm extraction 完成：classification {len(result.classification)}、"
        f"facts {len(result.key_facts)}、entities {len(result.entity_candidates)}、"
        f"relations {len(result.relation_candidates)}"
    )
    return QueryResponse(
        answer=answer,
        source=[],
        confidence=result.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="llm_extraction_summary", detail=detail)]),
    )
