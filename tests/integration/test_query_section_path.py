from __future__ import annotations

import pytest

import hks.commands.query as query_command
from hks.core.manifest import DerivedArtifacts, Manifest, ManifestEntry, save_manifest
from hks.core.paths import runtime_paths
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
