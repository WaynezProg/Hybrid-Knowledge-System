"""Normalize extracted text and split it into retrieval chunks."""

from __future__ import annotations

import re
from typing import Any

from hks.core.text_models import SIMPLE_EMBEDDING_MODEL, TextModelBackend, join_tokens
from hks.ingest.office_common import Segment

WHITESPACE_RE = re.compile(r"[ \t]+")
NEWLINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    lines = [
        WHITESPACE_RE.sub(" ", line).strip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    cleaned = "\n".join(lines)
    cleaned = NEWLINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def chunk(
    text: str,
    *,
    size: int = 512,
    overlap: int = 64,
    backend: TextModelBackend | None = None,
) -> list[str]:
    if not text.strip():
        return []

    model_backend = backend or TextModelBackend()
    if model_backend.model_name != SIMPLE_EMBEDDING_MODEL:
        token_ids = model_backend.encode_token_ids(text)
        if not token_ids:
            return []

        decoded_chunks: list[str] = []
        step = max(1, size - overlap)
        start = 0
        while start < len(token_ids):
            end = min(len(token_ids), start + size)
            decoded_chunks.append(model_backend.decode_token_ids(token_ids[start:end]))
            if end >= len(token_ids):
                break
            start += step
        return decoded_chunks

    tokens = model_backend.tokenize(text)
    if not tokens:
        return []

    chunks: list[str] = []
    step = max(1, size - overlap)
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + size)
        chunks.append(join_tokens(tokens[start:end]))
        if end >= len(tokens):
            break
        start += step
    return chunks


_SECTION_KINDS = {"heading", "sheet_header", "slide_header"}
_ISOLATED_KINDS = {"table_row", "notes", "placeholder"}


def segments_to_body(segments: list[Segment]) -> str:
    """Concatenate segment texts into a wiki-friendly markdown body.

    Preserves headers as-is, blank-line separates paragraph-like segments,
    keeps table rows consecutive. Used by pipeline when a parser produced
    segments instead of a single `body`.
    """

    if not segments:
        return ""
    parts: list[str] = []
    prev_kind: str | None = None
    for segment in segments:
        text = segment.text
        if not text:
            continue
        if segment.kind == "table_row" and prev_kind == "table_row":
            parts.append(text)
        else:
            if parts:
                parts.append("")  # blank line
            parts.append(text)
        prev_kind = segment.kind
    return "\n".join(parts).strip()


def _metadata_for_segment(segment: Segment, carry: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = dict(carry)
    meta["section_type"] = segment.kind
    for key in ("sheet_name", "slide_index", "row_index", "formula_only"):
        if key in segment.metadata:
            meta[key] = segment.metadata[key]
    return meta


def segment_aware_chunks(
    segments: list[Segment],
    *,
    size: int = 512,
    overlap: int = 64,
    backend: TextModelBackend | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Group segments into chunks while preserving sheet / slide metadata.

    Boundary rules (spec FR-021 / FR-031, research §9):
    - A `heading` / `sheet_header` / `slide_header` segment flushes the
      running buffer before being emitted as the first line of the next
      chunk; this keeps table rows and paragraphs in the same chunk as
      their immediate anchor.
    - Token budget (`size`) splits oversized sections by paragraph / row /
      placeholder boundaries; we never split a single segment.
    - `carry` metadata (latest sheet_name / slide_index) flows across
      chunks until a new sheet_header / slide_header resets it.
    """

    if not segments:
        return []

    model_backend = backend or TextModelBackend()
    chunks: list[tuple[str, dict[str, Any]]] = []
    buffer_segments: list[Segment] = []
    buffer_tokens = 0
    carry: dict[str, Any] = {}
    carry_lines: list[str] = []

    def _flush() -> None:
        nonlocal buffer_segments, buffer_tokens
        if not buffer_segments:
            return
        body_parts = [*carry_lines, *(s.text for s in buffer_segments if s.text)]
        body = "\n\n".join(part for part in body_parts if part).strip()
        if body:
            anchor = buffer_segments[0]
            chunks.append((body, _metadata_for_segment(anchor, carry)))
        buffer_segments = []
        buffer_tokens = 0

    for segment in segments:
        if segment.kind == "sheet_header":
            _flush()
            carry = {"sheet_name": segment.metadata.get("sheet_name", "")}
            carry_lines = [segment.text]
            continue
        if segment.kind == "slide_header":
            _flush()
            carry = {"slide_index": segment.metadata.get("slide_index", 0)}
            carry_lines = [segment.text]
            continue
        if segment.kind == "heading":
            _flush()
            heading_body = "\n\n".join([*carry_lines, segment.text]).strip()
            if heading_body:
                chunks.append((heading_body, _metadata_for_segment(segment, carry)))
            carry_lines = [*carry_lines[:1], segment.text] if carry_lines else [segment.text]
            continue

        segment_tokens = max(1, model_backend.count_tokens(segment.text))
        if segment.kind in _ISOLATED_KINDS:
            _flush()
            isolated_body = "\n\n".join([*carry_lines, segment.text]).strip()
            if isolated_body:
                chunks.append((isolated_body, _metadata_for_segment(segment, carry)))
            continue
        if buffer_tokens + segment_tokens > size and buffer_segments:
            _flush()
        buffer_segments.append(segment)
        buffer_tokens += segment_tokens

    _flush()
    del overlap  # chunk overlap is segment-bounded; retained for signature parity
    return chunks
