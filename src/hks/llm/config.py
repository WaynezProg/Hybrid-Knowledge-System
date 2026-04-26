"""Provider configuration and local-first gates for LLM extraction."""

from __future__ import annotations

import os
from typing import cast

from hks.errors import ExitCode, KSError
from hks.llm.models import (
    DEFAULT_FAKE_MODEL,
    DEFAULT_PROMPT_VERSION,
    ExtractionMode,
    LlmExtractionRequest,
    LlmProviderConfig,
)

SUPPORTED_MODES: frozenset[str] = frozenset(("preview", "store"))
SUPPORTED_PROVIDERS: frozenset[str] = frozenset(("fake", "fake-malformed", "fake-side-effect"))


def normalize_provider_id(value: str | None) -> str:
    provider_id = (value or os.environ.get("HKS_LLM_PROVIDER") or "fake").strip()
    if not provider_id:
        raise KSError(
            "LLM provider 不可為空",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return provider_id


def normalize_mode(value: str) -> ExtractionMode:
    if value not in SUPPORTED_MODES:
        raise KSError(
            f"mode 不合法：{value}",
            exit_code=ExitCode.USAGE,
            code="USAGE",
            details=[f"expected one of: {', '.join(sorted(SUPPORTED_MODES))}"],
        )
    return cast(ExtractionMode, value)


def build_provider_config(
    provider_id: str | None = None,
    *,
    model_id: str | None = None,
    timeout_seconds: int = 30,
) -> LlmProviderConfig:
    provider = normalize_provider_id(provider_id)
    model = model_id or os.environ.get("HKS_LLM_MODEL") or DEFAULT_FAKE_MODEL
    if provider in SUPPORTED_PROVIDERS:
        return LlmProviderConfig(
            provider_id=provider,
            model_id=model,
            timeout_seconds=timeout_seconds,
        )

    env_prefix = f"HKS_LLM_PROVIDER_{provider.upper().replace('-', '_')}"
    network_opt_in = os.environ.get("HKS_LLM_NETWORK_OPT_IN") == "1"
    api_key = os.environ.get(f"{env_prefix}_API_KEY")
    endpoint = os.environ.get(f"{env_prefix}_ENDPOINT")
    if not network_opt_in:
        raise KSError(
            f"hosted/network LLM provider `{provider}` requires HKS_LLM_NETWORK_OPT_IN=1",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    if not api_key:
        raise KSError(
            f"hosted/network LLM provider `{provider}` requires {env_prefix}_API_KEY",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    raise KSError(
        f"LLM provider `{provider}` is gated but not implemented in 008",
        exit_code=ExitCode.USAGE,
        code="USAGE",
        details=[f"endpoint: {endpoint or '<unset>'}"],
    )


def build_request(
    *,
    source_relpath: str,
    mode: str = "preview",
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    force_new_run: bool = False,
    requested_by: str | None = None,
) -> LlmExtractionRequest:
    return LlmExtractionRequest(
        source_relpath=source_relpath.strip(),
        mode=normalize_mode(mode),
        prompt_version=prompt_version or DEFAULT_PROMPT_VERSION,
        provider=build_provider_config(provider, model_id=model),
        force_new_run=force_new_run,
        requested_by=requested_by,
    )
