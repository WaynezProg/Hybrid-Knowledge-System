from __future__ import annotations

import pytest

from hks.core.paths import runtime_paths
from hks.core.text_models import TextModelBackend
from hks.storage.vector import VectorChunk, VectorStore


@pytest.mark.unit
@pytest.mark.us2
def test_vector_search_returns_similarity_hits(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    store = VectorStore(paths, backend=TextModelBackend("simple"))
    store.add_chunks(
        [
            VectorChunk(
                id="atlas-1",
                text="Clause 3.2 covers Atlas pricing constraints.",
                metadata={"source_relpath": "project-atlas.txt", "chunk_idx": 0},
            )
        ]
    )

    hits = store.search("clause 3.2 text", top_k=1)

    assert len(hits) == 1
    assert hits[0].chunk_id == "atlas-1"
    assert 0 < hits[0].similarity <= 1


@pytest.mark.unit
@pytest.mark.us2
def test_vector_search_returns_empty_list_for_empty_store(tmp_path) -> None:
    paths = runtime_paths(tmp_path / "ks")
    store = VectorStore(paths, backend=TextModelBackend("simple"))

    assert store.search("anything", top_k=1) == []
