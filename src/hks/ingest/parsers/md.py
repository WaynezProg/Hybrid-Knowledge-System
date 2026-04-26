"""Markdown parser."""

from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt

from hks.ingest.models import ParsedDocument


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    closing = text.find("\n---\n", len("---\n"))
    if closing == -1:
        return text
    return text[closing + len("\n---\n") :].lstrip()


def parse(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = _strip_frontmatter(text)
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
    return ParsedDocument(title=title, body=body, format="md")
