"""Validation helpers for wiki synthesis payloads."""

from __future__ import annotations

from hks.adapters.contracts import validate_wiki_candidate, validate_wiki_summary
from hks.errors import ExitCode, KSError
from hks.wiki_synthesis.models import WikiSynthesisCandidate, WikiSynthesisResult


def validate_candidate(candidate: WikiSynthesisCandidate) -> WikiSynthesisCandidate:
    try:
        validate_wiki_candidate(candidate.to_dict())
    except Exception as exc:
        raise KSError(
            "wiki synthesis candidate schema validation failed",
            exit_code=ExitCode.DATAERR,
            code="WIKI_CANDIDATE_INVALID",
            details=[str(exc)],
        ) from exc
    return candidate


def validate_result(result: WikiSynthesisResult) -> WikiSynthesisResult:
    try:
        validate_wiki_summary(result.to_detail())
    except Exception as exc:
        raise KSError(
            "wiki synthesis summary schema validation failed",
            exit_code=ExitCode.DATAERR,
            code="WIKI_SYNTHESIS_INVALID",
            details=[str(exc)],
        ) from exc
    return result
