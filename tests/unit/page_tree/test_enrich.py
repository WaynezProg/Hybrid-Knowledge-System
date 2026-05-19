"""Unit tests for LLM tree enrichment."""

from __future__ import annotations

import pytest

from hks.page_tree.enrich import enrich_tree
from hks.page_tree.model import PageTree, TreeNode


def _rule_tree() -> PageTree:
    return PageTree(
        source_relpath="doc.md",
        source_format="md",
        doc_title="Doc",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Chapter 1",
                level=1,
                start_offset=0,
                end_offset=100,
                children=[
                    TreeNode(
                        node_id="n1.1",
                        title="Section 1.1",
                        level=2,
                        start_offset=0,
                        end_offset=50,
                        children=[],
                        metadata={"kind": "section"},
                    )
                ],
                metadata={"kind": "chapter"},
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=2,
        source_sha256="abc",
    )


def _degenerate_tree() -> PageTree:
    return PageTree(
        source_relpath="flat.txt",
        source_format="txt",
        doc_title="Flat",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Flat",
                level=1,
                start_offset=0,
                end_offset=500,
                children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="def",
    )


class TestEnrichTree:
    def test_fake_provider_fills_summaries(self) -> None:
        tree = _rule_tree()
        source_text = "Chapter 1 content. " * 5 + "Section 1.1 detail. " * 3

        enriched = enrich_tree(tree, source_text, provider="fake")

        assert enriched.build_method == "llm"
        for node in enriched.flat_nodes():
            assert node.summary != ""

    def test_fake_provider_preserves_structure(self) -> None:
        tree = _rule_tree()

        enriched = enrich_tree(tree, "x" * 100, provider="fake")

        assert enriched.total_nodes == tree.total_nodes
        assert enriched.root_nodes[0].node_id == "n1"
        assert enriched.root_nodes[0].level == 1
        assert enriched.root_nodes[0].start_offset == 0
        assert enriched.root_nodes[0].end_offset == 100
        assert enriched.root_nodes[0].children[0].node_id == "n1.1"
        assert enriched.root_nodes[0].children[0].level == 2
        assert enriched.root_nodes[0].children[0].start_offset == 0
        assert enriched.root_nodes[0].children[0].end_offset == 50

    def test_fake_provider_copies_metadata_without_mutation_leak(self) -> None:
        tree = _rule_tree()

        enriched = enrich_tree(tree, "x" * 100, provider="fake")
        enriched.root_nodes[0].metadata["kind"] = "changed"

        assert tree.root_nodes[0].metadata["kind"] == "chapter"
        assert enriched.root_nodes[0].metadata["kind"] == "changed"

    def test_degenerate_tree_restructured(self) -> None:
        tree = _degenerate_tree()

        enriched = enrich_tree(tree, "A" * 500, provider="fake")

        assert enriched.build_method == "llm"
        assert enriched.total_nodes == 3
        assert [node.node_id for node in enriched.root_nodes] == ["n1", "n2", "n3"]
        assert all(node.level == 1 for node in enriched.root_nodes)
        assert all(node.summary != "" for node in enriched.root_nodes)

    def test_already_llm_skips_with_force_false(self) -> None:
        tree = _rule_tree()
        llm_tree = PageTree(
            source_relpath=tree.source_relpath,
            source_format=tree.source_format,
            doc_title=tree.doc_title,
            root_nodes=tree.root_nodes,
            build_method="llm",
            built_at=tree.built_at,
            total_nodes=tree.total_nodes,
            source_sha256=tree.source_sha256,
        )

        result = enrich_tree(llm_tree, "text", provider="fake", force=False)

        assert result is llm_tree

    def test_non_fake_provider_is_not_implemented(self) -> None:
        tree = _rule_tree()

        with pytest.raises(NotImplementedError):
            enrich_tree(tree, "text", provider="openai")
