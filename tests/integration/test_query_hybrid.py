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


@pytest.mark.integration
def test_route_mode_answers_through_the_lexical_route(
    cli_runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from hks.cli import app
    from hks.core.schema import validate

    docs = tmp_path / "docs"
    docs.mkdir()
    for index in range(8):
        (docs / f"note{index}.md").write_text(
            f"# Note {index}\n\nGeneral remarks about the planning cycle number {index}.\n",
            encoding="utf-8",
        )
    (docs / "incident.md").write_text(
        "# Incident\n\nTicket ERR-4012 was resolved by rotating the gateway token.\n",
        encoding="utf-8",
    )
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0

    monkeypatch.setenv("HKS_HYBRID_SEARCH", "route")
    result = cli_runner.invoke(app, ["query", "ERR-4012", "--writeback=no"])
    assert result.exit_code == 0, result.stdout
    payload = validate(json.loads(result.stdout))

    kinds = [step["kind"] for step in payload["trace"]["steps"]]
    assert "lexical_lookup" in kinds
    assert payload["source"] == ["lexical"] and payload["trace"]["route"] == "lexical"
    assert payload["evidence"][0] == {
        "source_relpath": "incident.md",
        "route": "lexical",
        "quote": payload["evidence"][0]["quote"],
        "section_path": "Incident",
    }

    monkeypatch.setenv("HKS_HYBRID_SEARCH", "fused")
    fused = json.loads(cli_runner.invoke(app, ["query", "ERR-4012", "--writeback=no"]).stdout)
    assert fused["source"] == ["vector"]
    assert "lexical_lookup" not in [step["kind"] for step in fused["trace"]["steps"]]
