"""Provider configuration and local-first gates for LLM extraction."""

from __future__ import annotations

from typing import cast

from hks.core.config import config_value
from hks.errors import ExitCode, KSError
from hks.llm.models import (
    DEFAULT_FAKE_MODEL,
    DEFAULT_PROMPT_VERSION,
    ExtractionMode,
    LlmExtractionRequest,
    LlmProviderConfig,
)

OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
SUPPORTED_MODES: frozenset[str] = frozenset(("preview", "store"))
FAKE_PROVIDERS: frozenset[str] = frozenset(
    ("fake", "fake-malformed", "fake-side-effect")
)
SUPPORTED_PROVIDERS: frozenset[str] = FAKE_PROVIDERS | frozenset(("openai",))


def normalize_provider_id(value: str | None) -> str:
    provider_id = (value or config_value("HKS_LLM_PROVIDER") or "fake").strip()
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
    model = model_id or config_value("HKS_LLM_MODEL") or _default_model(provider)
    if provider in FAKE_PROVIDERS:
        return LlmProviderConfig(
            provider_id=provider,
            model_id=model,
            timeout_seconds=timeout_seconds,
        )
    if provider == "openai":
        openai_api_key, endpoint = require_hosted_provider_credentials(provider)
        return LlmProviderConfig(
            provider_id=provider,
            model_id=model,
            endpoint=endpoint,
            network_opt_in=True,
            timeout_seconds=timeout_seconds,
            credential_status="present" if openai_api_key else "missing",
        )

    env_prefix = f"HKS_LLM_PROVIDER_{provider.upper().replace('-', '_')}"
    network_opt_in = config_value("HKS_LLM_NETWORK_OPT_IN") == "1"
    api_key = config_value(f"{env_prefix}_API_KEY")
    endpoint = config_value(f"{env_prefix}_ENDPOINT")
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
    return LlmProviderConfig(
        provider_id=provider,
        model_id=model,
        endpoint=endpoint,
        network_opt_in=network_opt_in,
        timeout_seconds=timeout_seconds,
        credential_status="present" if api_key else "missing",
    )


def _default_model(provider: str) -> str:
    if provider == "openai":
        return OPENAI_DEFAULT_MODEL
    return DEFAULT_FAKE_MODEL


def require_hosted_provider_credentials(provider: str) -> tuple[str, str | None]:
    env_prefix = f"HKS_LLM_PROVIDER_{provider.upper().replace('-', '_')}"
    if config_value("HKS_LLM_NETWORK_OPT_IN") != "1":
        raise KSError(
            f"hosted/network LLM provider `{provider}` requires HKS_LLM_NETWORK_OPT_IN=1",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )

    api_key = _hosted_provider_api_key(provider)
    if not api_key:
        raise KSError(
            f"hosted/network LLM provider `{provider}` requires {env_prefix}_API_KEY",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    return api_key, config_value(f"{env_prefix}_ENDPOINT")


def hosted_provider_ready(provider: str) -> bool:
    return (
        config_value("HKS_LLM_NETWORK_OPT_IN") == "1"
        and _hosted_provider_api_key(provider) is not None
    )


def _hosted_provider_api_key(provider: str) -> str | None:
    env_prefix = f"HKS_LLM_PROVIDER_{provider.upper().replace('-', '_')}"
    api_key = config_value(f"{env_prefix}_API_KEY")
    if provider == "openai":
        api_key = api_key or config_value("OPENAI_API_KEY")
    return api_key


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
