"""Normalize extracted text and split it into retrieval chunks."""

from __future__ import annotations

import re

from hks.core.text_models import SIMPLE_EMBEDDING_MODEL, TextModelBackend, join_tokens

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
