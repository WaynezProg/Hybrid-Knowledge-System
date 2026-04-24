"""Phase 1 lint stub."""

from __future__ import annotations

from hks.core.schema import QueryResponse, Trace


def run() -> QueryResponse:
    return QueryResponse(
        answer="lint 尚未實作，預計於 Phase 3 提供",
        source=[],
        confidence=0.0,
        trace=Trace(route="wiki", steps=[]),
    )
