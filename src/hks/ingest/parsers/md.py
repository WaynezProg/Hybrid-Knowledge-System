"""Markdown parser."""

from __future__ import annotations

import re
import shlex
from datetime import date, datetime
from pathlib import Path

from markdown_it import MarkdownIt
from ruamel.yaml import YAML

from hks.ingest.models import ParsedDocument
from hks.ingest.office_common import Segment

_DOCUMENT_METADATA_KEYS = {
    "hks_type",
    "date",
    "source_domain",
    "generator",
    "workspace_id",
    "memory_kind",
    "tool",
    "session_id",
    "evidence_id",
}
_SESSION_ENTRY_RE = re.compile(
    r"^\s*-\s+\[(?P<kind>[^\]]+)\]\s+(?P<text>.+?)\s+"
    r"(?:\((?P<paren_meta>[^)]*)\)|\{(?P<brace_meta>[^}]*)\})\s*$",
    re.MULTILINE,
)
_HEADING_RE = re.compile(r"^(?P<marker>#{1,6})\s+(?P<title>.+?)\s*$", re.MULTILINE)
_DATE_RE = re.compile(r"\b(?P<date>20\d{2}-\d{2}-\d{2})\b")
_ENTRY_KEY_ALIASES = {
    "workspace": "workspace_id",
    "evidence": "evidence_id",
    "source": "tool",
    "session": "session_id",
}
_SESSION_ENTRY_REQUIRED_KEYS = {"workspace_id", "evidence_id", "tool", "session_id"}


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    closing = text.find("\n---\n", len("---\n"))
    if closing == -1:
        return {}, text
    blob = text[len("---\n") : closing]
    metadata = _frontmatter_metadata(blob)
    return metadata, text[closing + len("\n---\n") :].lstrip()


def _frontmatter_metadata(blob: str) -> dict[str, str]:
    yaml = YAML(typ="safe")
    try:
        payload = yaml.load(blob) or {}
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    metadata: dict[str, str] = {}
    for key, value in payload.items():
        key_text = str(key).strip()
        if key_text not in _DOCUMENT_METADATA_KEYS:
            continue
        value_text = _metadata_value(value)
        if value_text:
            metadata[key_text] = value_text
    return metadata


def _metadata_value(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str | int | float | bool):
        return str(value).strip()
    return ""


def _session_segments(
    body: str,
    metadata: dict[str, str],
    path: Path,
) -> tuple[list[Segment], dict[str, str]]:
    entries: list[tuple[re.Match[str], dict[str, str]]] = []
    for entry in _SESSION_ENTRY_RE.finditer(body):
        raw_meta = entry.group("paren_meta") or entry.group("brace_meta") or ""
        pairs = _parse_entry_pairs(raw_meta)
        if _is_session_entry_pairs(pairs):
            entries.append((entry, pairs))
    if not entries:
        return [], dict(metadata)

    document_metadata = _session_document_metadata(body, metadata, path)
    segments: list[Segment] = []
    first_heading = _HEADING_RE.search(body)
    if first_heading is not None:
        level = len(first_heading.group("marker"))
        segments.append(
            Segment(
                kind="heading",
                text=f"{'#' * level} {first_heading.group('title').strip()}",
                metadata={"level": level, **document_metadata},
            )
        )

    for entry, pairs in entries:
        entry_metadata = _entry_metadata(
            kind=entry.group("kind"),
            pairs=pairs,
            document_metadata=document_metadata,
        )
        segments.append(
            Segment(
                kind="session_entry",
                text=entry.group("text").strip(),
                metadata=entry_metadata,
            )
        )
    return segments, document_metadata


def _session_document_metadata(
    body: str,
    metadata: dict[str, str],
    path: Path,
) -> dict[str, str]:
    detected_date = metadata.get("date") or _date_from_text(body) or _date_from_text(path.stem)
    session_metadata = dict(metadata)
    session_metadata.setdefault("hks_type", "session_daily")
    session_metadata.setdefault("source_domain", "session_memory")
    session_metadata.setdefault("generator", "session2memory")
    if detected_date:
        session_metadata["date"] = detected_date
    return session_metadata


def _date_from_text(text: str) -> str:
    match = _DATE_RE.search(text)
    return match.group("date") if match is not None else ""


def _entry_metadata(
    *,
    kind: str,
    pairs: dict[str, str],
    document_metadata: dict[str, str],
) -> dict[str, str]:
    metadata = dict(document_metadata)
    metadata["memory_kind"] = pairs.get("memory_kind") or kind.strip()
    for key, value in pairs.items():
        if key in {"workspace_id", "evidence_id", "tool", "session_id"}:
            metadata[key] = value
    return metadata


def _is_session_entry_pairs(pairs: dict[str, str]) -> bool:
    return _SESSION_ENTRY_REQUIRED_KEYS.issubset(pairs)


def _parse_entry_pairs(raw_meta: str) -> dict[str, str]:
    pairs = _parse_colon_entry_pairs(raw_meta)
    pairs.update(_parse_equals_entry_pairs(raw_meta))
    return pairs


def _parse_colon_entry_pairs(raw_meta: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in raw_meta.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = _normalize_entry_key(key)
        normalized_value = value.strip()
        if normalized_key and normalized_value:
            pairs[normalized_key] = normalized_value
    return pairs


def _parse_equals_entry_pairs(raw_meta: str) -> dict[str, str]:
    try:
        parts = shlex.split(raw_meta)
    except ValueError:
        parts = raw_meta.split()
    pairs: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.rstrip(",").split("=", 1)
        normalized_key = _normalize_entry_key(key)
        normalized_value = value.strip()
        if normalized_key and normalized_value:
            pairs[normalized_key] = normalized_value
    return pairs


def _normalize_entry_key(key: str) -> str:
    normalized = key.strip().lower()
    return _ENTRY_KEY_ALIASES.get(normalized, normalized)


def parse(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata, body = _split_frontmatter(text)
    title = ""
    tokens = MarkdownIt().parse(body)
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            inline = tokens[index + 1]
            if inline.type == "inline" and inline.content.strip():
                title = inline.content.strip()
                break
    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").strip() or path.stem
    segments, document_metadata = _session_segments(body, metadata, path)
    return ParsedDocument(
        title=title,
        body=body,
        format="md",
        segments=segments,
        metadata=document_metadata,
    )
