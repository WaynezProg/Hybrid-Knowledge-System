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

    def test_fake_provider_deep_copies_nested_metadata(self) -> None:
        tree = PageTree(
            source_relpath="doc.md",
            source_format="md",
            doc_title="Doc",
            root_nodes=[
                TreeNode(
                    node_id="n1",
                    title="Chapter",
                    level=1,
                    start_offset=0,
                    end_offset=10,
                    children=[
                        TreeNode(
                            node_id="n1.1",
                            title="Section",
                            level=2,
                            start_offset=0,
                            end_offset=5,
                            children=[],
                        )
                    ],
                    metadata={"labels": ["original"], "nested": {"kind": "chapter"}},
                )
            ],
            build_method="rule",
            built_at="2026-05-19T00:00:00Z",
            total_nodes=2,
            source_sha256="abc",
        )

        enriched = enrich_tree(tree, "x" * 10, provider="fake", force=True)
        enriched.root_nodes[0].metadata["labels"].append("changed")
        enriched.root_nodes[0].metadata["nested"]["kind"] = "changed"

        assert tree.root_nodes[0].metadata == {
            "labels": ["original"],
            "nested": {"kind": "chapter"},
        }

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

    def test_openai_provider_calls_llm_summarize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tree = _rule_tree()
        source_text = "Chapter 1 content. " * 5 + "Section 1.1 detail. " * 3

        def mock_summarize(text: str, title: str, provider: str, model: str | None) -> str:
            return f"LLM summary of {title}"

        monkeypatch.setattr(
            "hks.page_tree.enrich._llm_summarize", mock_summarize
        )

        enriched = enrich_tree(tree, source_text, provider="openai")

        assert enriched.build_method == "llm"
        assert enriched.root_nodes[0].summary == "LLM summary of Chapter 1"
        assert enriched.root_nodes[0].children[0].summary == "LLM summary of Section 1.1"

    def test_openai_provider_restructures_degenerate_tree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from typing import Any
        tree = _degenerate_tree()

        def mock_restructure(
            tree: Any, source_text: str, provider: str, model: str | None
        ) -> Any:
            from hks.page_tree.model import PageTree, TreeNode
            from hks.core.manifest import utc_now_iso

            nodes = [
                TreeNode(
                    node_id="llm-n1", title="Introduction", level=1,
                    start_offset=0, end_offset=250, children=[], summary="Intro",
                ),
                TreeNode(
                    node_id="llm-n2", title="Body", level=1,
                    start_offset=250, end_offset=500, children=[], summary="Body",
                ),
            ]
            return PageTree(
                source_relpath=tree.source_relpath,
                source_format=tree.source_format,
                doc_title=tree.doc_title,
                root_nodes=nodes,
                build_method="llm",
                built_at=utc_now_iso(),
                total_nodes=2,
                source_sha256=tree.source_sha256,
            )

        monkeypatch.setattr(
            "hks.page_tree.enrich._llm_restructure", mock_restructure
        )

        enriched = enrich_tree(tree, "A" * 500, provider="openai")

        assert enriched.build_method == "llm"
        assert enriched.total_nodes == 2
