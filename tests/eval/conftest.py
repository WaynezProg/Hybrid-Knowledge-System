"""Shared eval fixtures and env-gate skip logic."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hks.core.config import _nested_get, config_value, load_structured_config

OPENAI_KEY_ENV = "HKS_LLM_PROVIDER_OPENAI_API_KEY"


def _has_openai_access() -> bool:
    """Check that hosted OpenAI evals have both network opt-in and an API key."""
    if config_value("HKS_LLM_NETWORK_OPT_IN") != "1":
        return False

    # Check env vars directly (not via config_value, which may be
    # affected by autouse fixtures during collection).
    if os.environ.get(OPENAI_KEY_ENV) or os.environ.get("OPENAI_API_KEY"):
        return True
    if config_value(OPENAI_KEY_ENV) or config_value("OPENAI_API_KEY"):
        return True
    payload = load_structured_config()
    return bool(_nested_get(payload, ("embedding", "openai", "api_key")))


requires_openai = pytest.mark.skipif(
    not _has_openai_access(),
    reason=(
        f"Set HKS_LLM_NETWORK_OPT_IN=1 and {OPENAI_KEY_ENV} or OPENAI_API_KEY "
        "to run eval tests"
    ),
)


def _real_config_file() -> str | None:
    """Find the real hks.yaml from the repo (not the test-isolated one)."""
    # Walk up from this file to find the repo root config
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "hks.yaml"
        if candidate.exists():
            return str(candidate)
    return None


@pytest.fixture(autouse=True)
def _eval_restore_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override the test-isolation fixture to use real config for evals."""
    real_config = _real_config_file()
    if real_config:
        monkeypatch.setenv("HKS_CONFIG_FILE", real_config)
