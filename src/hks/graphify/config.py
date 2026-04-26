"""Configuration for 010 Graphify."""

from __future__ import annotations

from typing import cast

from hks.errors import ExitCode, KSError
from hks.graphify.models import (
    DEFAULT_ALGORITHM_VERSION,
    DEFAULT_FAKE_MODEL,
    GraphifyMode,
    GraphifyRequest,
)
from hks.llm.config import build_provider_config

SUPPORTED_MODES: frozenset[str] = frozenset(("preview", "store"))


def normalize_mode(value: str) -> GraphifyMode:
    if value not in SUPPORTED_MODES:
        raise KSError(
            f"mode 不合法：{value}",
            exit_code=ExitCode.USAGE,
            code="USAGE",
            details=[f"expected one of: {', '.join(sorted(SUPPORTED_MODES))}"],
        )
    return cast(GraphifyMode, value)


def build_request(
    *,
    mode: str = "preview",
    provider: str | None = None,
    model: str | None = None,
    algorithm_version: str | None = None,
    include_html: bool = True,
    include_report: bool = True,
    force_new_run: bool = False,
    requested_by: str | None = None,
) -> GraphifyRequest:
    return GraphifyRequest(
        mode=normalize_mode(mode),
        provider=build_provider_config(provider, model_id=model or DEFAULT_FAKE_MODEL),
        algorithm_version=algorithm_version or DEFAULT_ALGORITHM_VERSION,
        include_html=include_html,
        include_report=include_report,
        force_new_run=force_new_run,
        requested_by=requested_by,
    )
