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


def test_nested_relation_uses_most_specific_section_evidence_only() -> None:
    body = (
        "# Doc\n\n"
        "## Parent\n\n"
        "Parent Project affects Parent API.\n\n"
        "### Child\n\n"
        "Child Project affects Child API.\n\n"
        "Parent closing notes."
    )
    parent_start = body.index("## Parent")
    child_start = body.index("### Child")
    child_end = body.index("Parent closing notes.")
    tree = PageTree(
        source_relpath="doc.md",
        source_format="md",
        doc_title="Doc",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Parent",
                level=2,
                start_offset=parent_start,
                end_offset=len(body),
                children=[
                    TreeNode(
                        node_id="n1.1",
                        title="Child",
                        level=3,
                        start_offset=child_start,
                        end_offset=child_end,
                        children=[],
                    )
                ],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=2,
        source_sha256="x",
    )

    result = extract_document_graph(
        relpath="doc.md",
        title="Doc",
        body=body,
        wiki_slug="doc",
        page_tree=tree,
    )

    child_evidence = "Section: Parent > Child | Child Project affects Child API."
    parent_evidence = "Section: Parent | Child Project affects Child API."
    assert any(edge.evidence == child_evidence for edge in result.edges)
    assert not any(edge.evidence == parent_evidence for edge in result.edges)


def test_same_section_title_is_scoped_by_source_and_not_document_id() -> None:
    tree = PageTree(
        source_relpath="other.md",
        source_format="md",
        doc_title="Other",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Risks",
                level=2,
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

    section_result = extract_document_graph(
        relpath="other.md",
        title="Other",
        body="Project Atlas affects Billing API.",
        wiki_slug="other",
        page_tree=tree,
    )
    document_result = extract_document_graph(
        relpath="risks.md",
        title="Risks",
        body="Project Borealis affects Search API.",
        wiki_slug="risks",
    )

    section_node = next(
        node
        for node in section_result.nodes
        if node.label == "Risks" and node.source_relpaths == ["other.md"]
    )
    document_node = next(node for node in document_result.nodes if node.label == "Risks")
    assert section_node.id != document_node.id
    assert section_node.id != "document:risks"
    assert any(
        edge.relation == "belongs_to"
        and edge.source == section_node.id
        and edge.target != document_node.id
        for edge in section_result.edges
    )
