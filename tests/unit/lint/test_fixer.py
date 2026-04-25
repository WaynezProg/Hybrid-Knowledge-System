from __future__ import annotations

import pytest

from hks.lint.fixer import plan_fixes
from hks.lint.models import Finding


@pytest.mark.unit
def test_plan_fixes_groups_allowlisted_actions() -> None:
    planned, skipped = plan_fixes(
        [
            Finding.make("orphan_page", "extra", "extra page"),
            Finding.make("orphan_vector_chunk", "chunk-1", "extra chunk"),
            Finding.make(
                "graph_drift",
                "node-1",
                "orphan node",
                details={"kind": "orphan_node", "node_id": "node-1"},
            ),
            Finding.make(
                "graph_drift",
                "edge-1",
                "dangling edge",
                details={"kind": "dangling_edge", "edge_id": "edge-1"},
            ),
        ]
    )

    assert [action.action for action in planned] == [
        "rebuild_index",
        "prune_orphan_vector_chunks",
        "prune_orphan_graph_nodes",
        "prune_orphan_graph_edges",
    ]
    assert skipped == []


@pytest.mark.unit
def test_plan_fixes_skips_manifest_truth_unknown_categories() -> None:
    planned, skipped = plan_fixes(
        [
            Finding.make("manifest_wiki_mismatch", "missing", "missing page"),
            Finding.make("fingerprint_drift", "doc.txt", "old parser"),
        ]
    )

    assert planned == []
    assert [skip.reason for skip in skipped] == ["manifest_truth_unknown", "requires_manual"]
