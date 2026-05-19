"""Tree-aware graph extraction tests."""

from __future__ import annotations

from hks.graph.extract import extract_document_graph
from hks.page_tree.model import PageTree, TreeNode


def test_tree_nodes_become_section_entities_with_contextual_edges() -> None:
    body = (
        "# Doc\n\n"
        "## Risks\n\n"
        "Project Atlas affects Billing API.\n\n"
        "## Appendix\n\n"
        "Unrelated notes."
    )
    section_start = body.index("## Risks")
    section_end = body.index("## Appendix")
    tree = PageTree(
        source_relpath="doc.md",
        source_format="md",
        doc_title="Doc",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Risks",
                level=2,
                start_offset=section_start,
                end_offset=section_end,
                children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="x",
    )

    result = extract_document_graph(
        relpath="doc.md",
        title="Doc",
        body=body,
        wiki_slug="doc",
        page_tree=tree,
    )

    nodes_by_label = {node.label: node for node in result.nodes}
    section_node = nodes_by_label["Risks"]
    document_node = nodes_by_label["Doc"]
    assert section_node.type == "Document"

    assert any(
        edge.relation == "belongs_to"
        and edge.source == section_node.id
        and edge.target == document_node.id
        for edge in result.edges
    )
    assert any(
        edge.relation == "impacts"
        and edge.evidence == "Section: Risks | Project Atlas affects Billing API."
        for edge in result.edges
    )


def test_document_title_section_does_not_create_self_belongs_to_edge() -> None:
    tree = PageTree(
        source_relpath="doc.md",
        source_format="md",
        doc_title="Doc",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Doc",
                level=1,
                start_offset=0,
                end_offset=32,
                children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="x",
    )

    result = extract_document_graph(
        relpath="doc.md",
        title="Doc",
        body="Project Atlas affects Billing API.",
        wiki_slug="doc",
        page_tree=tree,
    )

    assert not any(
        edge.relation == "belongs_to" and edge.source == edge.target
        for edge in result.edges
    )
