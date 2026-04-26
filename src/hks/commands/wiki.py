"""Command wrappers for 009 wiki synthesis."""

from __future__ import annotations

from hks.adapters.contracts import validate_wiki_summary
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.wiki_synthesis.config import build_request
from hks.wiki_synthesis.service import synthesize


def run_synthesize(
    *,
    mode: str = "preview",
    source_relpath: str | None = None,
    extraction_artifact_id: str | None = None,
    candidate_artifact_id: str | None = None,
    target_slug: str | None = None,
    provider: str = "fake",
    model: str | None = None,
    prompt_version: str | None = None,
    force_new_run: bool = False,
    requested_by: str | None = None,
) -> QueryResponse:
    request = build_request(
        mode=mode,
        source_relpath=source_relpath,
        extraction_artifact_id=extraction_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
        target_slug=target_slug,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        force_new_run=force_new_run,
        requested_by=requested_by,
    )
    result = synthesize(request)
    detail = result.to_detail()
    validate_wiki_summary(detail)
    response = QueryResponse(
        answer=f"wiki synthesis {result.mode} 完成：{result.candidate.target_slug}",
        source=[],
        confidence=result.candidate.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="wiki_synthesis_summary", detail=detail)]),
    )
    conflict = (
        result.mode == "apply"
        and result.apply_result
        and result.apply_result.operation == "conflict"
    )
    if conflict:
        raise KSError(
            "wiki synthesis apply conflict",
            exit_code=ExitCode.GENERAL,
            code="WIKI_SYNTHESIS_CONFLICT",
            response=response,
        )
    if result.mode == "apply" and result.apply_result:
        return QueryResponse(
            answer=f"wiki synthesis apply 完成：{result.candidate.target_slug}",
            source=["wiki"],
            confidence=result.candidate.confidence,
            trace=Trace(
                route="wiki",
                steps=[TraceStep(kind="wiki_synthesis_summary", detail=detail)],
            ),
        )
    return QueryResponse(
        answer=response.answer,
        source=[],
        confidence=result.candidate.confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="wiki_synthesis_summary", detail=detail)]),
    )
