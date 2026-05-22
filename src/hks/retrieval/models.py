"""Shared retrieval data models."""

from __future__ import annotations

from dataclasses import dataclass

from hks.core.schema import Route


@dataclass(slots=True)
class Candidate:
    text: str
    source_route: Route
    score: float
    metadata: dict[str, object]
