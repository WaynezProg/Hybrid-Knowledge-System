"""Chroma-backed vector store with deterministic local fallback embeddings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import chromadb

from hks.core.paths import RuntimePaths, runtime_paths
from hks.core.text_models import TextModelBackend

COLLECTION_NAME = "hks_phase1"


@dataclass(slots=True)
class VectorChunk:
    id: str
    text: str
    metadata: dict[str, str | int | float | bool]


@dataclass(slots=True)
class SearchHit:
    chunk_id: str
    text: str
    similarity: float
    metadata: dict[str, Any]


class VectorStore:
    def __init__(
        self,
        paths: RuntimePaths | None = None,
        *,
        backend: TextModelBackend | None = None,
    ) -> None:
        self.paths = paths or runtime_paths()
        self.backend = backend or TextModelBackend()
        self.paths.vector_db.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.paths.vector_db))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[VectorChunk]) -> list[str]:
        if not chunks:
            return []

        ids = [chunk.id for chunk in chunks]
        embeddings = self.backend.embed_texts([chunk.text for chunk in chunks])
        self.collection.upsert(
            ids=ids,
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata for chunk in chunks],
            embeddings=cast(list[Sequence[float]], embeddings),
        )
        return ids

    def count(self) -> int:
        return int(self.collection.count())

    def list_ids(self) -> list[str]:
        result = cast(dict[str, Any], self.collection.get())
        return [str(chunk_id) for chunk_id in result.get("ids", [])]

    def delete(self, ids: list[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def search(self, query: str, *, top_k: int = 5) -> list[SearchHit]:
        if self.count() == 0:
            return []

        query_embedding = self.backend.embed_query(query)
        result = cast(
            dict[str, Any],
            self.collection.query(
                query_embeddings=cast(list[Sequence[float]], [query_embedding]),
                n_results=top_k,
                include=["documents", "distances", "metadatas"],
            ),
        )
        ids = cast(list[list[str]], result.get("ids") or [[]])[0]
        documents = cast(list[list[str]], result.get("documents") or [[]])[0]
        distances = cast(list[list[float]], result.get("distances") or [[]])[0]
        metadatas = cast(list[list[dict[str, Any]]], result.get("metadatas") or [[]])[0]
        hits: list[SearchHit] = []
        for chunk_id, document, distance, metadata in zip(
            ids,
            documents,
            distances,
            metadatas,
            strict=False,
        ):
            similarity = max(0.0, 1.0 - float(distance))
            hits.append(
                SearchHit(
                    chunk_id=str(chunk_id),
                    text=str(document),
                    similarity=similarity,
                    metadata=dict(metadata or {}),
                )
            )
        return hits
