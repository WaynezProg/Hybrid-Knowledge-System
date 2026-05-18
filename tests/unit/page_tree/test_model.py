"""Unit tests for page_tree data model."""

from __future__ import annotations

from hks.page_tree.model import PageTree, TreeNode


class TestTreeNode:
    def test_leaf_node_to_dict(self) -> None:
        node = TreeNode(
            node_id="n1",
            title="Introduction",
            level=1,
            start_offset=0,
            end_offset=500,
            children=[],
        )

        result = node.to_dict()

        assert result["node_id"] == "n1"
        assert result["title"] == "Introduction"
        assert result["level"] == 1
        assert result["start_offset"] == 0
        assert result["end_offset"] == 500
        assert result["children"] == []
        assert result["summary"] == ""
        assert result["metadata"] == {}

    def test_nested_node_to_dict(self) -> None:
        child = TreeNode(
            node_id="n1.1",
            title="Background",
            level=2,
            start_offset=0,
            end_offset=200,
            children=[],
        )
        parent = TreeNode(
            node_id="n1",
            title="Introduction",
            level=1,
            start_offset=0,
            end_offset=500,
            children=[child],
        )

        result = parent.to_dict()

        assert len(result["children"]) == 1
        assert result["children"][0]["node_id"] == "n1.1"

    def test_node_with_metadata(self) -> None:
        node = TreeNode(
            node_id="n2",
            title="Chapter 2",
            level=1,
            start_offset=500,
            end_offset=1200,
            children=[],
            metadata={"page_start": 4, "page_end": 7},
        )

        result = node.to_dict()

        assert result["metadata"]["page_start"] == 4

    def test_from_dict_round_trip(self) -> None:
        node = TreeNode(
            node_id="n1",
            title="Test",
            level=1,
            start_offset=0,
            end_offset=100,
            children=[
                TreeNode(
                    node_id="n1.1",
                    title="Sub",
                    level=2,
                    start_offset=0,
                    end_offset=50,
                    children=[],
                    summary="A sub-section.",
                )
            ],
            summary="Top level.",
            metadata={"page_start": 1},
        )

        restored = TreeNode.from_dict(node.to_dict())

        assert restored.node_id == node.node_id
        assert restored.children[0].summary == "A sub-section."
        assert restored.metadata == {"page_start": 1}


class TestPageTree:
    def test_to_dict(self) -> None:
        tree = PageTree(
            source_relpath="report.pdf",
            source_format="pdf",
            doc_title="Q1 Report",
            root_nodes=[
                TreeNode(
                    node_id="n1",
                    title="Summary",
                    level=1,
                    start_offset=0,
                    end_offset=300,
                    children=[],
                )
            ],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=1,
            source_sha256="abc123",
        )

        result = tree.to_dict()

        assert result["source_relpath"] == "report.pdf"
        assert result["total_nodes"] == 1
        assert len(result["root_nodes"]) == 1

    def test_from_dict_round_trip(self) -> None:
        tree = PageTree(
            source_relpath="doc.md",
            source_format="md",
            doc_title="Doc",
            root_nodes=[],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=0,
            source_sha256="def456",
        )

        restored = PageTree.from_dict(tree.to_dict())

        assert restored.source_relpath == tree.source_relpath
        assert restored.build_method == tree.build_method

    def test_json_round_trip(self) -> None:
        tree = PageTree(
            source_relpath="slides.pptx",
            source_format="pptx",
            doc_title="Slides",
            root_nodes=[
                TreeNode(
                    node_id="n1",
                    title="Slide 1",
                    level=1,
                    start_offset=0,
                    end_offset=100,
                    children=[],
                    metadata={"slide_index": 0},
                )
            ],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=1,
            source_sha256="ghi789",
        )

        json_str = tree.to_json()
        restored = PageTree.from_json(json_str)

        assert restored.root_nodes[0].metadata["slide_index"] == 0

    def test_flat_nodes(self) -> None:
        child = TreeNode(
            node_id="n1.1",
            title="Sub",
            level=2,
            start_offset=0,
            end_offset=50,
            children=[],
        )
        parent = TreeNode(
            node_id="n1",
            title="Top",
            level=1,
            start_offset=0,
            end_offset=100,
            children=[child],
        )
        tree = PageTree(
            source_relpath="t.txt",
            source_format="txt",
            doc_title="T",
            root_nodes=[parent],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=2,
            source_sha256="x",
        )

        flat = tree.flat_nodes()

        assert len(flat) == 2
        assert flat[0].node_id == "n1"
        assert flat[1].node_id == "n1.1"

    def test_find_node_for_offset(self) -> None:
        child = TreeNode(
            node_id="n1.1",
            title="Sub",
            level=2,
            start_offset=0,
            end_offset=50,
            children=[],
        )
        parent = TreeNode(
            node_id="n1",
            title="Top",
            level=1,
            start_offset=0,
            end_offset=100,
            children=[child],
        )
        tree = PageTree(
            source_relpath="t.txt",
            source_format="txt",
            doc_title="T",
            root_nodes=[parent],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=2,
            source_sha256="x",
        )

        assert tree.find_node_for_offset(25).node_id == "n1.1"
        assert tree.find_node_for_offset(75).node_id == "n1"
        assert tree.find_node_for_offset(150) is None

    def test_section_path(self) -> None:
        child = TreeNode(
            node_id="n2.1",
            title="Revenue",
            level=2,
            start_offset=100,
            end_offset=200,
            children=[],
        )
        parent = TreeNode(
            node_id="n2",
            title="Finance",
            level=1,
            start_offset=100,
            end_offset=300,
            children=[child],
        )
        tree = PageTree(
            source_relpath="r.pdf",
            source_format="pdf",
            doc_title="R",
            root_nodes=[parent],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=2,
            source_sha256="x",
        )

        assert tree.section_path("n2.1") == "Finance > Revenue"
        assert tree.section_path("n2") == "Finance"
        assert tree.section_path("n999") is None
