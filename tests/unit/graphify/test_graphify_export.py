from __future__ import annotations

import json

from hks.graphify.export import render_html, render_report
from hks.graphify.models import (
    GraphifyAuditFinding,
    GraphifyCommunity,
    GraphifyEdge,
    GraphifyGraph,
    GraphifyNode,
)


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


def test_graphify_html_uses_fused_explorer_shell() -> None:
    html = render_html(_graph())

    assert "<title>Graphify Explorer · HKS</title>" in html
    assert "class=\"brand-glyph\"" in html
    assert "id=\"status-line\"" in html
    assert "--accent-bright: #c4a6ff;" in html


def test_graphify_html_keeps_payload_safe_for_untrusted_labels() -> None:
    unsafe = 'Project "</script><img src=x onerror=alert(1)>'
    html = render_html(
        GraphifyGraph(
            generated_at="2026-04-26T00:00:00+00:00",
            input_layers=["wiki", "graph"],
            nodes=[
                GraphifyNode(
                    id="wiki:project-atlas",
                    label=unsafe,
                    kind="wiki_page",
                    source_layer="wiki",
                    source_ref='wiki/pages/"atlas".md',
                    community_id="community:001",
                ),
                GraphifyNode(
                    id="entity:mobile-gateway",
                    label="Mobile Gateway",
                    kind="entity",
                    source_layer="graph",
                    source_ref="graph:mobile-gateway",
                    community_id="community:001",
                ),
            ],
            edges=[
                GraphifyEdge(
                    id="edge:1",
                    source="wiki:project-atlas",
                    target="entity:mobile-gateway",
                    relation='depends_on "quoted"',
                    evidence="EXTRACTED",
                    confidence_score=0.9,
                    weight=1.0,
                    source_layer="graph",
                    source_ref="graph:edge:1",
                    rationale=unsafe,
                )
            ],
            communities=[
                GraphifyCommunity(
                    community_id="community:001",
                    label=unsafe,
                    summary=unsafe,
                    node_ids=["wiki:project-atlas", "entity:mobile-gateway"],
                    representative_edge_ids=["edge:1"],
                    classification_method="deterministic",
                    confidence_score=1.0,
                )
            ],
            audit_findings=[
                GraphifyAuditFinding(
                    severity="warning",
                    code='unsafe-"code"',
                    message=unsafe,
                    source_ref='raw/"atlas".md',
                )
            ],
        )
    )

    payload = html.split('<script type="application/json" id="graphify-data">', 1)[1].split(
        "</script>",
        1,
    )[0]
    data = json.loads(payload)
    assert data["nodes"][0]["label"] == unsafe
    assert "</script><img" not in html
    assert "<img src=x" not in html
    assert "onclick=\"selectNodeById" not in html


def test_graphify_report_separates_evidence_counts() -> None:
    report = render_report(_graph())

    assert "EXTRACTED edges" in report
    assert "AMBIGUOUS edges" in report
