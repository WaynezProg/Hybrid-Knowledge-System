"""Shared eval fixtures and env-gate skip logic."""

from __future__ import annotations

import os

import pytest

OPENAI_KEY_ENV = "HKS_LLM_PROVIDER_OPENAI_API_KEY"

requires_openai = pytest.mark.skipif(
    not os.environ.get(OPENAI_KEY_ENV) and not os.environ.get("OPENAI_API_KEY"),
    reason=f"Set {OPENAI_KEY_ENV} or OPENAI_API_KEY to run eval tests",
)
