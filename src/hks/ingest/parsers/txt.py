"""Plain text parser."""

from __future__ import annotations

from pathlib import Path

from hks.ingest.models import ParsedDocument


def parse(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem.replace("-", " ").replace("_", " ").strip() or path.stem
    return ParsedDocument(title=title, body=text, format="txt")
