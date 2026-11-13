"""Hybrid retrieval against a real vector store."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.paths import runtime_paths
from hks.storage.vector import VectorChunk, VectorStore


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VectorStore:
    monkeypatch.setenv("KS_ROOT", str(tmp_path / "ks"))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")
    vector_store = VectorStore(runtime_paths())
    vector_store.add_chunks(
        [
            VectorChunk(
                "a:0", "Atlas rollout plan for the spring release", {"source_relpath": "a.md"}
            ),
            VectorChunk(
                "b:0", "Ticket ERR-4012 is fixed by rotating the token", {"source_relpath": "b.md"}
            ),
            VectorChunk("c:0", "風險評估與時程安排", {"source_relpath": "c.md"}),
        ]
    )
    return vector_store


def test_all_chunks_and_similarities_read_what_was_stored(store: VectorStore) -> None:
    chunks = {chunk.chunk_id: chunk for chunk in store.all_chunks()}
    assert set(chunks) == {"a:0", "b:0", "c:0"}
    assert chunks["b:0"].metadata == {"source_relpath": "b.md"}

    dense = {hit.chunk_id: hit.similarity for hit in store.search("ERR-4012 token", top_k=3)}
    stored = store.similarities("ERR-4012 token", ["b:0", "c:0", "missing"])
    assert set(stored) == {"b:0", "c:0"}
    assert stored["b:0"] == pytest.approx(dense["b:0"], abs=1e-4), (
        "same measure as the dense search"
    )
    assert store.similarities("anything", []) == {}
