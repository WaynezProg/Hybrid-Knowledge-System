"""Bounded Chinese vocabulary and explicit, request-local workspace aliases.

Only comparison/search text is normalized. Stored sources and returned evidence keep
their original spelling; no embeddings or persisted index need to be rewritten.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from hks.errors import ExitCode, KSError

_SYNONYMS = {
    "等候": "等待",
    "熱鍵": "快捷鍵",
    "兼容": "相容",
    "隱憂": "風險",
    "隐忧": "風險",
    "风险": "風險",
    "改寫": "重寫",
    "狀況": "狀態",
    "状况": "狀態",
}
_ALIASES: ContextVar[dict[str, str] | None] = ContextVar("hks_query_aliases", default=None)
_FACETS = {
    "風險": ("風險", "risk", "risks", "隱憂"),
    "狀態": ("狀態", "status", "healthy", "stable", "正常", "目前", "focus"),
}


def has_subject_constraints(question: str) -> bool:
    asked = normalize(question)
    return any(facet in asked for facet in _FACETS) or any(
        re.search(_pattern(canonical), asked) for canonical in set((_ALIASES.get() or {}).values())
    )


def has_entity_and_facet_match(question: str, text: str) -> bool:
    asked = normalize(question)
    return (
        any(facet in asked for facet in _FACETS)
        and any(
            re.search(_pattern(canonical), asked)
            for canonical in set((_ALIASES.get() or {}).values())
        )
        and satisfies_subject(question, text)
    )


def _pattern(term: str) -> str:
    left = r"(?<![a-z0-9])" if term[0].isascii() and term[0].isalnum() else ""
    right = r"(?![a-z0-9])" if term[-1].isascii() and term[-1].isalnum() else ""
    return left + re.escape(term) + right


def normalize(text: str) -> str:
    return normalize_query(text).casefold()


def normalize_query(text: str) -> str:
    """Retain the case of untouched names such as IT/US in search questions."""
    replacements = {**_SYNONYMS, **(_ALIASES.get() or {})}
    return _compiled(tuple(replacements)).sub(
        lambda match: replacements[match.group().casefold()], text
    )


@lru_cache(maxsize=32)
def _compiled(terms: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        "|".join(_pattern(term) for term in sorted(terms, key=len, reverse=True)),
        re.IGNORECASE | re.ASCII,
    )


@contextmanager
def language_scope(root: Path) -> Iterator[None]:
    path = root / "query_aliases.json"
    aliases: dict[str, str] = {}
    if path.exists():
        try:
            from hks.retrieval.bm25 import identifier_terms

            if path.stat().st_size > 65536:
                raise ValueError("alias file exceeds 64 KiB")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("expected canonical-name -> alias-list object")
            for canonical, variants in payload.items():
                if not canonical.strip() or not isinstance(variants, list):
                    raise ValueError("expected nonempty canonical name and alias list")
                for variant in [canonical, *variants]:
                    if not isinstance(variant, str) or not variant.strip():
                        raise ValueError("aliases must be nonempty strings")
                    term, target = variant.strip().casefold(), canonical.strip().casefold()
                    if identifier_terms(term) or identifier_terms(target):
                        raise ValueError("ticket/version identifiers cannot be aliased")
                    if term in aliases and aliases[term] != target:
                        raise ValueError("ambiguous alias")
                    aliases[term] = target
        except (OSError, ValueError, TypeError) as exc:
            raise KSError(
                "無法讀取 query_aliases.json",
                exit_code=ExitCode.DATAERR,
                code="CONFIG_ERROR",
                hint=str(exc),
            ) from exc
    token = _ALIASES.set(aliases)
    try:
        yield
    finally:
        _ALIASES.reset(token)


def satisfies_subject(question: str, text: str) -> bool:
    """Require explicitly configured entities and the requested risk/status facet.

    This precedes candidate truncation/reranking. A high score for another service or
    another aspect of the same project cannot satisfy the missing subject.
    """
    asked, present = normalize(question), normalize(text)
    for canonical in set((_ALIASES.get() or {}).values()):
        if re.search(_pattern(canonical), asked) and not re.search(_pattern(canonical), present):
            return False
    for facet, spellings in _FACETS.items():
        if facet in asked and not any(
            re.search(_pattern(normalize(word)), present) for word in spellings
        ):
            return False
    return True
