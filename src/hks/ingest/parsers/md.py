"""Markdown parser."""

from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt

from hks.ingest.models import ParsedDocument


def parse(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = ""
    tokens = MarkdownIt().parse(text)
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            inline = tokens[index + 1]
            if inline.type == "inline" and inline.content.strip():
                title = inline.content.strip()
                break
    if not title:
        title = path.stem.replace("-", " ").replace("_", " ").strip() or path.stem
    return ParsedDocument(title=title, body=text, format="md")
