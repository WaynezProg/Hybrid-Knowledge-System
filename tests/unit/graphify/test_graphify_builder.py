from __future__ import annotations

from hks.adapters import core
from hks.graphify.builder import build_graph


def test_graphify_builder_reads_existing_hks_layers(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    graph, fingerprint, source = build_graph()

    assert graph.nodes
    assert fingerprint
    assert source
