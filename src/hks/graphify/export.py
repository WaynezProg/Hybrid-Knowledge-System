"""Static artifact rendering for Graphify."""

from __future__ import annotations

import html
import json

from hks.graphify.models import GraphifyGraph


def render_html(graph: GraphifyGraph) -> str:
    nodes = graph.nodes[:500]
    edges = graph.edges[:1000]
    items = "\n".join(
        f"<li><strong>{html.escape(node.label)}</strong> "
        f"<code>{html.escape(node.kind)}</code> "
        f"<span>{html.escape(node.community_id or '')}</span></li>"
        for node in nodes
    )
    edge_items = "\n".join(
        f"<li>{html.escape(edge.source)} -> {html.escape(edge.target)} "
        f"({html.escape(edge.relation)}, {html.escape(edge.evidence)}, "
        f"{edge.confidence_score:.2f})</li>"
        for edge in edges
    )
    payload = html.escape(json.dumps(graph.to_dict(), ensure_ascii=False))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HKS Graphify</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; }}
    code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 4px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <h1>HKS Graphify</h1>
  <p>{len(graph.nodes)} nodes · {len(graph.edges)} edges · {len(graph.communities)} communities</p>
  <div class="grid">
    <section><h2>Nodes</h2><ul>{items}</ul></section>
    <section><h2>Edges</h2><ul>{edge_items}</ul></section>
  </div>
  <script type="application/json" id="graphify-data">{payload}</script>
</body>
</html>
"""


def render_report(graph: GraphifyGraph) -> str:
    evidence_counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0}
    for edge in graph.edges:
        evidence_counts[edge.evidence] += 1
    lines = [
        "# GRAPH_REPORT",
        "",
        f"- Nodes: {len(graph.nodes)}",
        f"- Edges: {len(graph.edges)}",
        f"- Communities: {len(graph.communities)}",
        f"- EXTRACTED edges: {evidence_counts['EXTRACTED']}",
        f"- INFERRED edges: {evidence_counts['INFERRED']}",
        f"- AMBIGUOUS edges: {evidence_counts['AMBIGUOUS']}",
        "",
        "## Communities",
        "",
    ]
    for community in graph.communities:
        lines.append(
            f"- {community.community_id}: {community.label} "
            f"({len(community.node_ids)} nodes, confidence {community.confidence_score:.2f})"
        )
    lines.extend(["", "## Audit Findings", ""])
    if not graph.audit_findings:
        lines.append("- none")
    for finding in graph.audit_findings:
        lines.append(f"- {finding.severity}: {finding.code} - {finding.message}")
    return "\n".join(lines) + "\n"
