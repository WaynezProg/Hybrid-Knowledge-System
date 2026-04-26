"""Versioned prompt contract for 008 extraction."""

from __future__ import annotations

from hks.llm.models import DEFAULT_PROMPT_VERSION

EXTRACTION_PROMPT_TEMPLATE = """
You are extracting structured personal knowledge from one source.
Return JSON only. Do not perform side effects. Do not write files.

Required fields:
- classification
- summary_candidate
- key_facts
- entity_candidates
- relation_candidates
- confidence
""".strip()


def prompt_version() -> str:
    return DEFAULT_PROMPT_VERSION


def build_prompt(*, source_relpath: str, content: str) -> str:
    return f"{EXTRACTION_PROMPT_TEMPLATE}\n\nSource: {source_relpath}\n\n{content[:4000]}"
