"""Provider configuration for 009 wiki synthesis."""

from __future__ import annotations

from typing import cast

from hks.errors import ExitCode, KSError
from hks.llm.config import build_provider_config
from hks.wiki_synthesis.models import (
    DEFAULT_FAKE_MODEL,
    DEFAULT_PROMPT_VERSION,
    WikiSynthesisMode,
    WikiSynthesisRequest,
)

SUPPORTED_MODES: frozenset[str] = frozenset(("preview", "store", "apply"))


def normalize_mode(value: str) -> WikiSynthesisMode:
    if value not in SUPPORTED_MODES:
        raise KSError(
            f"mode 不合法：{value}",
            exit_code=ExitCode.USAGE,
            code="USAGE",
            details=[f"expected one of: {', '.join(sorted(SUPPORTED_MODES))}"],
        )
    return cast(WikiSynthesisMode, value)


def build_request(
    *,
    mode: str = "preview",
    source_relpath: str | None = None,
    extraction_artifact_id: str | None = None,
    candidate_artifact_id: str | None = None,
    target_slug: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    force_new_run: bool = False,
    requested_by: str | None = None,
) -> WikiSynthesisRequest:
    normalized_mode = normalize_mode(mode)
    if normalized_mode == "apply":
        if not candidate_artifact_id or not candidate_artifact_id.strip():
            raise KSError(
                "apply 需要 --candidate-artifact-id",
                exit_code=ExitCode.NOINPUT,
                code="NOINPUT",
                hint="run `ks wiki synthesize --mode store` first",
            )
    elif not (source_relpath and source_relpath.strip()) and not (
        extraction_artifact_id and extraction_artifact_id.strip()
    ):
        raise KSError(
            "preview/store 需要 source_relpath 或 extraction_artifact_id",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks llm classify <source-relpath> --mode store` first",
        )
    return WikiSynthesisRequest(
        mode=normalized_mode,
        source_relpath=source_relpath.strip() if source_relpath else None,
        extraction_artifact_id=extraction_artifact_id.strip() if extraction_artifact_id else None,
        candidate_artifact_id=candidate_artifact_id.strip() if candidate_artifact_id else None,
        target_slug=target_slug.strip() if target_slug else None,
        prompt_version=prompt_version or DEFAULT_PROMPT_VERSION,
        provider=build_provider_config(provider, model_id=model or DEFAULT_FAKE_MODEL),
        force_new_run=force_new_run,
        requested_by=requested_by,
    )
