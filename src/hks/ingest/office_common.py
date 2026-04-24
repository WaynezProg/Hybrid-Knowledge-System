"""Shared primitives for Office parsers (docx / xlsx / pptx).

Centralizes:
- Placeholder prefix constants (spec FR-012 / FR-023 / FR-032,
  contracts/office-placeholder-prefix.md).
- `SkippedSegment` / `Segment` dataclasses and `SegmentKind` / `SkippedSegmentType`
  Literals.
- Helpers: `build_placeholder()`, `to_markdown_table()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SegmentKind = Literal[
    "paragraph",
    "heading",
    "list_item",
    "table_row",
    "sheet_header",
    "slide_header",
    "notes",
    "placeholder",
]

SkippedSegmentType = Literal[
    "image",
    "embedded_object",
    "smartart",
    "macros",
    "video",
    "audio",
    "chart",
    "pivot",
    "empty_slide",
]

# Placeholder prefixes — must stay ASCII and lowercase. See
# contracts/office-placeholder-prefix.md. Key = logical type, value = prefix
# literal WITHOUT the trailing payload and closing bracket.
PLACEHOLDER_PREFIXES: dict[str, str] = {
    "image": "[image: ",
    "embedded_object": "[embedded object: ",
    "smartart": "[smartart: ",
    "macros": "[macros: ",
    "video": "[video: ",
    "audio": "[audio: ",
    "chart": "[chart: ",
    "pivot": "[pivot: ",
}

# Default payload for types that have no meaningful per-occurrence detail.
_DEFAULT_PAYLOAD: dict[str, str] = {
    "macros": "skipped",
    "video": "skipped",
    "audio": "skipped",
    "chart": "skipped",
    "pivot": "skipped",
}


@dataclass(slots=True)
class Segment:
    kind: SegmentKind
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkippedSegment:
    type: SkippedSegmentType
    count: int = 1
    location: str | None = None


def build_placeholder(kind: SkippedSegmentType, payload: str | None = None) -> str:
    """Construct a placeholder literal per the contract.

    `empty_slide` is intentionally rejected — it has no in-flow placeholder
    (fully empty slides only emit a `SkippedSegment` record).
    """

    if kind == "empty_slide":
        raise ValueError("empty_slide has no in-flow placeholder; emit a SkippedSegment only")
    prefix = PLACEHOLDER_PREFIXES[kind]
    body = payload if payload is not None else _DEFAULT_PAYLOAD.get(kind, "")
    # Ensure the payload never closes the placeholder early.
    body = body.replace("]", " ")
    return f"{prefix}{body}]"


def to_markdown_table(header: list[str], rows: list[list[str]]) -> str:
    """Render a markdown table. Header cells and row cells are rendered verbatim.

    Returns a string with `\n`-terminated lines; does not append a trailing
    newline. Empty `rows` still renders header + separator (useful for
    per-row chunking where the row is appended by the caller).
    """

    def _row(cells: list[str]) -> str:
        escaped = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
        return "| " + " | ".join(escaped) + " |"

    lines: list[str] = [_row(header), "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend(_row(cells) for cells in rows)
    return "\n".join(lines)


def merge_skipped(existing: list[SkippedSegment], incoming: SkippedSegment) -> None:
    """Accumulate skipped segments by type (location-free aggregate).

    Detailed per-location records stay in `incoming.location`; callers that
    want aggregated counts (for log.md) use this to collapse identical types.
    """

    for segment in existing:
        if segment.type == incoming.type and segment.location is None and incoming.location is None:
            segment.count += incoming.count
            return
    existing.append(incoming)
