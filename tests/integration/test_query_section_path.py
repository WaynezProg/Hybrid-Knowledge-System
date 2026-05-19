from __future__ import annotations

from pathlib import Path

import pytest

import hks.commands.query as query_command
from hks.core.manifest import (
    DerivedArtifacts,
    Manifest,
    ManifestEntry,
    load_manifest,
    save_manifest,
)
from hks.core.paths import runtime_paths
from hks.ingest.pipeline import ingest
from hks.page_tree.model import PageTree, TreeNode
from hks.page_tree.store import TreeStore
from hks.storage.vector import SearchHit, VectorStore


@pytest.mark.integration
def test_vector_hit_trace_includes_section_path_and_page_range(
    tmp_ks_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_ks_root)
    relpath = "reports/launch-plan.md"
    tree = PageTree(
        source_relpath=relpath,
        source_format="md",
        doc_title="Launch Plan",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Launch Plan",
                level=1,
                start_offset=0,
                end_offset=500,
                children=[
                    TreeNode(
                        node_id="n1.1",
                        title="Risk Controls",
                        level=2,
                        start_offset=120,
                        end_offset=300,
                        children=[],
                        metadata={"page_start": 4, "page_end": 6},
                    )
                ],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00+00:00",
        total_nodes=2,
        source_sha256="abc123",
    )
    tree_slug = TreeStore(paths).save(relpath, tree)
    save_manifest(
        Manifest(
            entries={
                relpath: ManifestEntry(
                    relpath=relpath,
                    sha256="abc123",
                    format="md",
                    size_bytes=128,
                    ingested_at="2026-05-19T00:00:00+00:00",
                    derived=DerivedArtifacts(
                        vector_ids=["launch-plan:0"],
                        page_tree=tree_slug,
                    ),
                )
            }
        ),
        paths.manifest,
    )

    monkeypatch.setattr(query_command, "route_query", lambda *_args: _vector_decision())
    monkeypatch.setattr(VectorStore, "count", lambda *_args: 1)
    monkeypatch.setattr(
        VectorStore,
        "search",
        lambda *_args, **_kwargs: [
            SearchHit(
                chunk_id="launch-plan:0",
                text="clause 7.4 requires risk controls before launch.",
                similarity=0.91,
                metadata={
                    "source_relpath": relpath,
                    "tree_node_id": "n1.1",
                    "tree_node_title": "Risk Controls",
                },
            )
        ],
    )

    response = query_command.run("clause 7.4 risk controls", writeback="no")

    vector_detail = next(
        step.detail for step in response.trace.steps if step.kind == "vector_lookup"
    )
    assert vector_detail["source_relpath"] == relpath
    assert vector_detail["top_k"] == 5
    assert vector_detail["top_similarity"] == 0.91
    assert vector_detail["section_path"] == "Launch Plan > Risk Controls"
    assert vector_detail["page_range"] == {"start": 4, "end": 6}


@pytest.mark.integration
def test_vector_section_context_uses_relpath_specific_tree_after_same_basename_ingest(
    tmp_path: Path,
    tmp_ks_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = tmp_path / "docs"
    (docs / "a").mkdir(parents=True)
    (docs / "b").mkdir(parents=True)
    (docs / "a" / "report.md").write_text(
        "# Alpha Manual\n\nIntro.\n\n## Alpha Controls\n\nclause 9 alpha safeguards.\n",
        encoding="utf-8",
    )
    (docs / "b" / "report.md").write_text(
        "# Beta Manual\n\nIntro.\n\n## Beta Controls\n\nclause 9 beta safeguards.\n",
        encoding="utf-8",
    )
    ingest(docs)
    paths = runtime_paths(tmp_ks_root)
    manifest = load_manifest(paths.manifest)
    alpha_entry = manifest.entries["a/report.md"]
    beta_entry = manifest.entries["b/report.md"]
    assert alpha_entry.derived.page_tree is not None
    assert beta_entry.derived.page_tree is not None
    assert alpha_entry.derived.page_tree != beta_entry.derived.page_tree

    alpha_tree = TreeStore(paths).load(alpha_entry.derived.page_tree)
    alpha_node = next(node for node in alpha_tree.flat_nodes() if node.title == "Alpha Controls")

    _patch_vector_hit(
        monkeypatch,
        SearchHit(
            chunk_id="a-report:0",
            text="clause 9 alpha safeguards.",
            similarity=0.88,
            metadata={
                "source_relpath": "a/report.md",
                "tree_node_id": alpha_node.node_id,
                "tree_node_title": alpha_node.title,
            },
        ),
    )

    response = query_command.run("clause 9 alpha safeguards", writeback="no")

    vector_detail = _vector_detail(response)
    assert vector_detail["source_relpath"] == "a/report.md"
    assert vector_detail["section_path"] == "Alpha Manual > Alpha Controls"


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["missing", "stale"])
def test_vector_section_context_fail_opens_for_missing_or_stale_tree(
    tmp_ks_root,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    paths = runtime_paths(tmp_ks_root)
    tree = _tree(
        relpath="report.md",
        sha256="tree-sha",
        metadata={"page_start": 1, "page_end": 2},
    )
    tree_slug = TreeStore(paths).save("report.md", tree)
    if mode == "missing":
        TreeStore(paths).delete(tree_slug)
        entry_sha = "tree-sha"
    else:
        entry_sha = "manifest-sha"
    _save_manifest(paths.manifest, relpath="report.md", tree_slug=tree_slug, sha256=entry_sha)
    _patch_vector_hit(
        monkeypatch,
        SearchHit(
            chunk_id="report:0",
            text="clause stale provenance.",
            similarity=0.86,
            metadata={"source_relpath": "report.md", "tree_node_id": "n1.1"},
        ),
    )

    response = query_command.run("clause stale provenance", writeback="no")

    vector_detail = _vector_detail(response)
    assert vector_detail["source_relpath"] == "report.md"
    assert "section_path" not in vector_detail
    assert "page_range" not in vector_detail


@pytest.mark.integration
def test_vector_section_context_omits_page_range_when_page_metadata_is_partial(
    tmp_ks_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_ks_root)
    tree = _tree(relpath="partial.md", sha256="abc123", metadata={"page_start": 7})
    tree_slug = TreeStore(paths).save("partial.md", tree)
    _save_manifest(paths.manifest, relpath="partial.md", tree_slug=tree_slug, sha256="abc123")
    _patch_vector_hit(
        monkeypatch,
        SearchHit(
            chunk_id="partial:0",
            text="clause partial page metadata.",
            similarity=0.9,
            metadata={"source_relpath": "partial.md", "tree_node_id": "n1.1"},
        ),
    )

    response = query_command.run("clause partial page metadata", writeback="no")

    vector_detail = _vector_detail(response)
    assert vector_detail["section_path"] == "Manual > Controls"
    assert "page_range" not in vector_detail


def _vector_decision():
    return type(
        "VectorDecision",
        (),
        {
            "route": "vector",
            "secondary": None,
            "steps": [],
        },
    )()


def _patch_vector_hit(monkeypatch: pytest.MonkeyPatch, hit: SearchHit) -> None:
    monkeypatch.setattr(query_command, "route_query", lambda *_args: _vector_decision())
    monkeypatch.setattr(VectorStore, "count", lambda *_args: 1)
    monkeypatch.setattr(VectorStore, "search", lambda *_args, **_kwargs: [hit])


def _vector_detail(response) -> dict[str, object]:
    return next(step.detail for step in response.trace.steps if step.kind == "vector_lookup")


def _tree(relpath: str, sha256: str, metadata: dict[str, int]) -> PageTree:
    return PageTree(
        source_relpath=relpath,
        source_format="md",
        doc_title="Manual",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Manual",
                level=1,
                start_offset=0,
                end_offset=500,
                children=[
                    TreeNode(
                        node_id="n1.1",
                        title="Controls",
                        level=2,
                        start_offset=120,
                        end_offset=300,
                        children=[],
                        metadata=metadata,
                    )
                ],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00+00:00",
        total_nodes=2,
        source_sha256=sha256,
    )


def _save_manifest(path: Path, *, relpath: str, tree_slug: str, sha256: str) -> None:
    save_manifest(
        Manifest(
            entries={
                relpath: ManifestEntry(
                    relpath=relpath,
                    sha256=sha256,
                    format="md",
                    size_bytes=128,
                    ingested_at="2026-05-19T00:00:00+00:00",
                    derived=DerivedArtifacts(vector_ids=[f"{tree_slug}:0"], page_tree=tree_slug),
                )
            }
        ),
        path,
    )
