"""Unit tests for _build_writeback_context evidence collection."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.commands.query import _build_writeback_context
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.storage.wiki import WikiStore


def _make_response(
    *,
    steps: list[TraceStep] | None = None,
    evidence: list[dict[str, object]] | None = None,
) -> QueryResponse:
    return QueryResponse(
        answer="test answer",
        source=["wiki"],
        confidence=0.9,
        trace=Trace(route="wiki", steps=steps or []),
        evidence=evidence or [],
    )


@pytest.mark.unit
def test_writeback_context_collects_relpaths_from_trace_steps(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))
    store.write_page(
        title="Atlas",
        summary="atlas summary",
        body="# Atlas\n\ncontent",
        source_relpath="atlas.txt",
        origin="ingest",
    )
    response = _make_response(
        steps=[
            TraceStep(
                kind="wiki_lookup",
                detail={"hit": True, "slug": "atlas", "source_relpath": "atlas.txt"},
            ),
        ],
    )
    context = _build_writeback_context(response, store)
    assert "atlas" in context.related_slugs


@pytest.mark.unit
def test_writeback_context_collects_relpaths_from_evidence(tmp_ks_root: Path) -> None:
    """Evidence items (e.g. from page_tree winners) must contribute to related slugs."""
    store = WikiStore(runtime_paths(tmp_ks_root))
    store.write_page(
        title="Atlas",
        summary="atlas summary",
        body="# Atlas\n\ncontent",
        source_relpath="atlas.txt",
        origin="ingest",
    )
    response = _make_response(
        evidence=[
            {"source_relpath": "atlas.txt", "route": "page_tree", "quote": "some text"},
        ],
    )
    context = _build_writeback_context(response, store)
    assert "atlas" in context.related_slugs


@pytest.mark.unit
def test_writeback_context_deduplicates_trace_and_evidence(tmp_ks_root: Path) -> None:
    """Same relpath from both trace step and evidence should only produce one slug."""
    store = WikiStore(runtime_paths(tmp_ks_root))
    store.write_page(
        title="Atlas",
        summary="atlas summary",
        body="# Atlas\n\ncontent",
        source_relpath="atlas.txt",
        origin="ingest",
    )
    response = _make_response(
        steps=[
            TraceStep(
                kind="vector_lookup",
                detail={"source_relpath": "atlas.txt"},
            ),
        ],
        evidence=[
            {"source_relpath": "atlas.txt", "route": "page_tree", "quote": "text"},
        ],
    )
    context = _build_writeback_context(response, store)
    assert context.related_slugs.count("atlas") == 1


@pytest.mark.unit
def test_writeback_context_handles_empty_evidence(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))
    response = _make_response()
    context = _build_writeback_context(response, store)
    assert context.related_slugs == []


@pytest.mark.unit
def test_writeback_context_skips_evidence_without_source_relpath(tmp_ks_root: Path) -> None:
    store = WikiStore(runtime_paths(tmp_ks_root))
    response = _make_response(
        evidence=[
            {"route": "graph", "quote": "some text"},  # no source_relpath
        ],
    )
    context = _build_writeback_context(response, store)
    assert context.related_slugs == []
