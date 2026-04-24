"""Transform parsed text into wiki content and vector chunks."""

from __future__ import annotations

from pathlib import Path

from hks.ingest.models import ExtractedDocument, ParsedDocument


def summarize(text: str, *, max_chars: int = 80) -> str:
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return cleaned[:max_chars] if cleaned else ""


def extract(
    *,
    relpath: str,
    sha256: str,
    parsed: ParsedDocument,
    normalized_text: str,
    chunks: list[str],
    chunk_metadata: list[dict[str, object]] | None = None,
) -> ExtractedDocument:
    title = parsed.title.strip() or Path(relpath).stem
    summary = summarize(normalized_text) or title
    body = normalized_text.strip()
    if not body.startswith("# "):
        body = f"# {title}\n\n{body}"
    _ = sha256
    return ExtractedDocument(
        title=title,
        summary=summary,
        body=body,
        chunks=chunks,
        chunk_metadata=list(chunk_metadata or [{} for _ in chunks]),
    )
