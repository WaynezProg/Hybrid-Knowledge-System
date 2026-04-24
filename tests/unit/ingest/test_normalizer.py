from __future__ import annotations

import pytest

from hks.core.text_models import TextModelBackend, simple_tokenize
from hks.ingest.normalizer import chunk, normalize_text


@pytest.mark.unit
def test_normalize_text_collapses_whitespace() -> None:
    text = "alpha   beta\n\n\n gamma\t delta "

    normalized = normalize_text(text)

    assert normalized == "alpha beta\n\ngamma delta"


@pytest.mark.unit
def test_chunk_respects_overlap() -> None:
    backend = TextModelBackend("simple")
    text = " ".join(f"token{i}" for i in range(30))

    chunks = chunk(text, size=10, overlap=2, backend=backend)

    assert len(chunks) >= 3
    first_tokens = simple_tokenize(chunks[0])
    second_tokens = simple_tokenize(chunks[1])
    assert first_tokens[-2:] == second_tokens[:2]
