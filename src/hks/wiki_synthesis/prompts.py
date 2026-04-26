"""Versioned prompt contract placeholder for 009."""

from __future__ import annotations

from hks.wiki_synthesis.models import DEFAULT_PROMPT_VERSION


def build_prompt(*, prompt_version: str = DEFAULT_PROMPT_VERSION) -> str:
    return f"{prompt_version}: synthesize a human-readable wiki page from validated artifacts"
