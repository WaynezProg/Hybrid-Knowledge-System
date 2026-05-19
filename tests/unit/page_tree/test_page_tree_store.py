"""Unit tests for page_tree store."""

from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.paths import runtime_paths
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore


def _sample_tree(relpath: str = "doc.md") -> PageTree:
    return PageTree(
        source_relpath=relpath,
        source_format="md",
        doc_title="Test Doc",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Intro",
                level=1,
                start_offset=0,
                end_offset=100,
                children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="abc123",
    )


class TestTreeStore:
    def test_save_and_load(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)
        tree = _sample_tree()

        slug = store.save("doc.md", tree)
        loaded = store.load(slug)

        assert slug == "doc"
        assert (paths.page_trees / "doc.json").exists()
        assert loaded.source_relpath == "doc.md"
        assert loaded.total_nodes == 1
        assert loaded.root_nodes[0].title == "Intro"

    def test_delete(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)
        slug = store.save("doc.md", _sample_tree())

        assert store.exists(slug)
        store.delete(slug)

        assert not store.exists(slug)

    def test_list_slugs_returns_sorted_json_stems(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)
        store.save("b.md", _sample_tree("b.md"))
        store.save("a.md", _sample_tree("a.md"))
        paths.page_trees.joinpath("ignored.txt").write_text("x", encoding="utf-8")

        assert store.list_slugs() == ["a", "b"]

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)

        with pytest.raises(FileNotFoundError):
            store.load("nonexistent")

    def test_slug_uses_existing_wiki_convention_for_relpath_stem(self, tmp_path: Path) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)

        slug = store.save("folder/My Report_v2.md", _sample_tree("folder/My Report_v2.md"))

        assert slug == "folder-my-report-v2"

    def test_slug_is_based_on_relpath_to_avoid_same_basename_collision(
        self, tmp_path: Path
    ) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)

        first_slug = store.save("a/report.md", _sample_tree("a/report.md"))
        second_slug = store.save("b/report.md", _sample_tree("b/report.md"))

        assert first_slug == "a-report"
        assert second_slug == "b-report"
        assert store.load(first_slug).source_relpath == "a/report.md"
        assert store.load(second_slug).source_relpath == "b/report.md"

    @pytest.mark.parametrize("slug", ["", ".", "..", "../manifest", "nested/tree", r"nested\\tree"])
    @pytest.mark.parametrize("method", ["load", "delete", "exists"])
    def test_rejects_unsafe_slug_without_touching_outside_files(
        self, tmp_path: Path, slug: str, method: str
    ) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)
        sentinel = paths.root / "manifest.json"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("keep", encoding="utf-8")

        with pytest.raises(ValueError):
            getattr(store, method)(slug)

        assert sentinel.read_text(encoding="utf-8") == "keep"

    @pytest.mark.parametrize("method", ["load", "delete", "exists"])
    def test_rejects_absolute_slug_without_touching_outside_files(
        self, tmp_path: Path, method: str
    ) -> None:
        paths = runtime_paths(tmp_path / "ks")
        store = TreeStore(paths)
        outside = tmp_path / "outside.json"
        outside.write_text(_sample_tree("outside.md").to_json(), encoding="utf-8")

        with pytest.raises(ValueError):
            getattr(store, method)(str(outside.with_suffix("")))

        loaded = PageTree.from_json(outside.read_text(encoding="utf-8"))
        assert loaded.source_relpath == "outside.md"
