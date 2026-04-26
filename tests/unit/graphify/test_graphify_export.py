from __future__ import annotations

from hks.graphify.export import render_html, render_report
from hks.graphify.models import GraphifyCommunity, GraphifyGraph, GraphifyNode


def _graph() -> GraphifyGraph:
    return GraphifyGraph(
        generated_at="2026-04-26T00:00:00+00:00",
        input_layers=["wiki"],
        nodes=[
            GraphifyNode(
                id="wiki:project-atlas",
                label="Project Atlas",
                kind="wiki_page",
                source_layer="wiki",
                source_ref="wiki/pages/project-atlas.md",
                community_id="community:001",
            )
        ],
        edges=[],
        communities=[
            GraphifyCommunity(
                community_id="community:001",
                label="Project Atlas",
                summary="summary",
                node_ids=["wiki:project-atlas"],
                representative_edge_ids=[],
                classification_method="deterministic",
                confidence_score=1.0,
            )
        ],
    )


def test_graphify_html_has_no_remote_dependency() -> None:
    html = render_html(_graph())

    assert "https://" not in html
    assert "<script src=" not in html


def test_graphify_report_separates_evidence_counts() -> None:
    report = render_report(_graph())

    assert "EXTRACTED edges" in report
    assert "AMBIGUOUS edges" in report
