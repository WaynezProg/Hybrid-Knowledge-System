"""Test tree-assisted wiki search."""

from __future__ import annotations

from pathlib import Path

from hks.core.paths import runtime_paths
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore
from hks.storage.wiki import WikiStore


class TestTreeAssistedSearch:
    def test_tree_summaries_boost_search(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        wiki_store = WikiStore(paths)
        tree_store = TreeStore(paths)

        wiki_store.write_page(
            title="Finance Report",
            summary="Quarterly results",
            body="Operating margin notes for Q1.",
            source_relpath="finance.pdf",
            origin="ingest",
        )
        tree_store.save(
            "finance.pdf",
            PageTree(
                source_relpath="finance.pdf",
                source_format="pdf",
                doc_title="Finance Report",
                root_nodes=[
                    TreeNode(
                        node_id="n1",
                        title="Revenue Breakdown",
                        level=1,
                        start_offset=0,
                        end_offset=100,
                        children=[],
                        summary="Detailed quarterly revenue by product line.",
                    )
                ],
                build_method="rule",
                built_at="2026-05-19T00:00:00Z",
                total_nodes=1,
                source_sha256="x",
            ),
        )

        assert wiki_store.search("revenue breakdown") is None

        result = wiki_store.search("revenue breakdown", tree_store=tree_store)

        assert result is not None
        assert result.title == "Finance Report"

    def test_tree_load_failure_is_skipped(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        wiki_store = WikiStore(paths)
        tree_store = TreeStore(paths)

        wiki_store.write_page(
            title="Stable Page",
            summary="No matching text",
            body="No matching body.",
            source_relpath="stable.pdf",
            origin="ingest",
        )
        tree_store.save(
            "stable.pdf",
            PageTree(
                source_relpath="stable.pdf",
                source_format="pdf",
                doc_title="Stable Page",
                root_nodes=[],
                build_method="rule",
                built_at="2026-05-19T00:00:00Z",
                total_nodes=0,
                source_sha256="x",
            ),
        )
        for tree_path in paths.page_trees.glob("*.json"):
            tree_path.write_text("{invalid json", encoding="utf-8")

        result = wiki_store.search("stable", tree_store=tree_store)

        assert result is not None
        assert result.title == "Stable Page"

    def test_tree_hits_merge_with_existing_wiki_score(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        wiki_store = WikiStore(paths)
        tree_store = TreeStore(paths)

        wiki_store.write_page(
            title="Generic Report",
            summary="Revenue note",
            body="Short revenue context.",
            source_relpath="generic.pdf",
            origin="ingest",
        )
        wiki_store.write_page(
            title="Finance Report",
            summary="Quarterly results",
            body="Operating margin notes.",
            source_relpath="finance.pdf",
            origin="ingest",
        )
        tree_store.save(
            "finance.pdf",
            PageTree(
                source_relpath="finance.pdf",
                source_format="pdf",
                doc_title="Finance Report",
                root_nodes=[
                    TreeNode(
                        node_id="n1",
                        title="Revenue Breakdown",
                        level=1,
                        start_offset=0,
                        end_offset=100,
                        children=[],
                        summary="Detailed revenue breakdown by product line.",
                    )
                ],
                build_method="rule",
                built_at="2026-05-19T00:00:00Z",
                total_nodes=1,
                source_sha256="x",
            ),
        )

        result = wiki_store.search("revenue breakdown", tree_store=tree_store)

        assert result is not None
        assert result.title == "Finance Report"

    def test_tree_match_limits_wiki_scoring_to_matched_sources(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        wiki_store = WikiStore(paths)
        tree_store = TreeStore(paths)

        wiki_store.write_page(
            title="Revenue Breakdown Revenue Breakdown",
            summary="Revenue breakdown revenue breakdown revenue breakdown",
            body="Revenue breakdown revenue breakdown revenue breakdown",
            source_relpath="generic.pdf",
            origin="ingest",
        )
        wiki_store.write_page(
            title="Finance Report",
            summary="Quarterly results",
            body="Operating margin notes.",
            source_relpath="finance.pdf",
            origin="ingest",
        )
        tree_store.save(
            "finance.pdf",
            PageTree(
                source_relpath="finance.pdf",
                source_format="pdf",
                doc_title="Finance Report",
                root_nodes=[
                    TreeNode(
                        node_id="n1",
                        title="Revenue Breakdown",
                        level=1,
                        start_offset=0,
                        end_offset=100,
                        children=[],
                        summary="Tree-level revenue breakdown.",
                    )
                ],
                build_method="rule",
                built_at="2026-05-19T00:00:00Z",
                total_nodes=1,
                source_sha256="x",
            ),
        )

        result = wiki_store.search("revenue breakdown", tree_store=tree_store)

        assert result is not None
        assert result.source_relpath == "finance.pdf"

    def test_stale_tree_match_does_not_suppress_wiki_search(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        wiki_store = WikiStore(paths)
        tree_store = TreeStore(paths)

        wiki_store.write_page(
            title="Revenue Playbook",
            summary="Revenue breakdown guidance",
            body="Use product-line revenue breakdown for planning.",
            source_relpath="playbook.md",
            origin="ingest",
        )
        tree_store.save(
            "deleted.pdf",
            PageTree(
                source_relpath="deleted.pdf",
                source_format="pdf",
                doc_title="Deleted Report",
                root_nodes=[
                    TreeNode(
                        node_id="n1",
                        title="Revenue Breakdown",
                        level=1,
                        start_offset=0,
                        end_offset=100,
                        children=[],
                        summary="Stale tree summary matching revenue breakdown.",
                    )
                ],
                build_method="rule",
                built_at="2026-05-19T00:00:00Z",
                total_nodes=1,
                source_sha256="x",
            ),
        )

        result = wiki_store.search("revenue breakdown", tree_store=tree_store)

        assert result is not None
        assert result.source_relpath == "playbook.md"
