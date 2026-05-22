"""Unit tests for graph candidate retrieval."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from hks.retrievers.graph import collect_graph_candidates


def test_collect_graph_returns_candidate_on_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    graph_store = MagicMock()
    edge = MagicMock()
    edge.evidence = "A impacts B"
    edge.source_relpath = "dep.md"
    graph_payload = MagicMock()
    graph_payload.edges = {"e1": edge}
    graph_store.load.return_value = graph_payload

    mock_result = MagicMock()
    mock_result.answer = "A impacts B"
    mock_result.confidence = 0.88
    mock_result.relpaths = ["dep.md"]
    mock_result.node_ids = ["n1", "n2"]
    mock_result.edge_ids = ["e1"]
    mock_result.relations = ["impacts"]

    monkeypatch.setattr("hks.retrievers.graph.answer_query", lambda q, gs: mock_result)

    candidates, steps = collect_graph_candidates("impact analysis", graph_store=graph_store)

    assert len(candidates) == 1
    assert candidates[0].source_route == "graph"
    assert candidates[0].metadata["edge_ids"] == ["e1"]
    assert candidates[0].metadata["evidence_by_relpath"] == {"dep.md": "A impacts B"}
    assert steps[0].kind == "graph_lookup"
    assert steps[0].detail["hit"] is True


def test_collect_graph_returns_empty_on_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    graph_store = MagicMock()
    monkeypatch.setattr("hks.retrievers.graph.answer_query", lambda q, gs: None)

    candidates, steps = collect_graph_candidates("no match", graph_store=graph_store)

    assert candidates == []
    assert steps[0].kind == "graph_lookup"
    assert steps[0].detail["hit"] is False
