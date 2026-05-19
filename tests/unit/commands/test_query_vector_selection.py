"""Unit tests for vector hit selection."""

from __future__ import annotations

from hks.commands.query import _choose_vector_hit
from hks.storage.vector import SearchHit


def test_vector_hit_selection_prefers_more_lexical_matches_over_similarity_noise() -> None:
    broad_hit = SearchHit(
        chunk_id="png:0",
        text="Owner Iris appears in the PNG image.",
        similarity=0.99,
        metadata={"source_format": "png"},
    )
    precise_hit = SearchHit(
        chunk_id="jpg:0",
        text="Owner Mia appears in the JPG image.",
        similarity=0.91,
        metadata={"source_format": "jpg"},
    )

    chosen = _choose_vector_hit("detail Owner Mia", [broad_hit, precise_hit])

    assert chosen == precise_hit
