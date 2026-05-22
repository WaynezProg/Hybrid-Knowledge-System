"""Chroma-backed vector store with deterministic local fallback embeddings."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import chromadb

from hks.core.paths import RuntimePaths, runtime_paths
from hks.core.text_models import TextModelBackend

_COLLECTION_NAME_MAX_LENGTH = 63


def _collection_segment(value: object) -> str:
    segment = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return segment or "unknown"


def collection_name_for_backend(backend: TextModelBackend) -> str:
    prefix = "hks_v1"
    dimension = _collection_segment(backend.embedding_dimension)
    suffix = f"__{dimension}"
    available_model_length = _COLLECTION_NAME_MAX_LENGTH - len(prefix) - len(suffix) - 4
    model_slug = _collection_segment(backend.model_name_slug)
    if len(model_slug) > available_model_length:
        digest = hashlib.sha1(backend.model_name.encode("utf-8")).hexdigest()[:8]
        trimmed_length = max(1, available_model_length - len(digest) - 1)
        model_slug = f"{model_slug[:trimmed_length].rstrip('_')}_{digest}"
    return f"{prefix}__{model_slug}{suffix}"


COLLECTION_NAME = collection_name_for_backend(TextModelBackend("simple"))


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
        self.collection_name = collection_name_for_backend(self.backend)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": "cosine",
                "hks:embedding_model": self.backend.model_name,
                "hks:embedding_dimension": str(self.backend.embedding_dimension),
            },
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

    def has_ids(self, ids: list[str]) -> bool:
        if not ids:
            return False
        result = cast(dict[str, Any], self.collection.get(ids=ids))
        found_ids = {str(chunk_id) for chunk_id in result.get("ids", [])}
        return set(ids).issubset(found_ids)

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
