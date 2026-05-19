"""Test new relation types: causes, contradicts, succeeds."""

from __future__ import annotations

from hks.core.paths import runtime_paths
from hks.graph.extract import extract_document_graph
from hks.graph.query import answer_query
from hks.graph.store import GraphStore
from hks.page_tree.model import PageTree, TreeNode


class TestNewRelationTypes:
    def test_causes_relation(self) -> None:
        result = extract_document_graph(
            relpath="t.md",
            title="T",
            body="供應鏈中斷導致出貨延遲。Supply chain disruption causes shipping delay.",
            wiki_slug="t",
        )
        relation_types = {edge.relation for edge in result.edges}
        assert "causes" in relation_types

    def test_contradicts_relation(self) -> None:
        result = extract_document_graph(
            relpath="t.md",
            title="T",
            body=(
                "報告指出成長，但實際數據與預期矛盾。"
                "The report shows growth however actual data contradicts projections."
            ),
            wiki_slug="t",
        )
        relation_types = {edge.relation for edge in result.edges}
        assert "contradicts" in relation_types

    def test_succeeds_relation(self) -> None:
        result = extract_document_graph(
            relpath="t.md",
            title="T",
            body="Phase 1 之後接續 Phase 2。Phase 1 followed by Phase 2.",
            wiki_slug="t",
        )
        relation_types = {edge.relation for edge in result.edges}
        assert "succeeds" in relation_types


def test_graph_query_prefers_and_renders_new_relation_types(tmp_ks_root) -> None:
    artifacts = extract_document_graph(
        relpath="relations.md",
        title="Relations",
        body=(
            "Supply shock causes shipping delay.\n"
            "Actual usage contradicts capacity plan.\n"
            "Phase 1 followed by Phase 2."
        ),
        wiki_slug="relations",
    )
    store = GraphStore(runtime_paths(tmp_ks_root))
    store.replace_document("relations.md", artifacts)

    cause = answer_query("what cause shipping delay", store)
    assert cause is not None
    assert cause.relations == ["causes"]
    assert "造成" in cause.answer
    cause_zh = answer_query("什麼導致 shipping delay", store)
    assert cause_zh is not None
    assert cause_zh.relations == ["causes"]

    contradict = answer_query("capacity plan contradict evidence", store)
    assert contradict is not None
    assert contradict.relations == ["contradicts"]
    assert "矛盾" in contradict.answer
    contradict_zh = answer_query("capacity plan 有什麼矛盾", store)
    assert contradict_zh is not None
    assert contradict_zh.relations == ["contradicts"]

    succeed = answer_query("what follows Phase 1", store)
    assert succeed is not None
    assert succeed.relations == ["succeeds"]
    assert "接續" in succeed.answer
    succeed_alias = answer_query("what succeeds Phase 1", store)
    assert succeed_alias is not None
    assert succeed_alias.relations == ["succeeds"]
    succeed_zh = answer_query("Phase 1 後續接續什麼", store)
    assert succeed_zh is not None
    assert succeed_zh.relations == ["succeeds"]


def test_causes_and_impacts_subjects_use_event_default() -> None:
    result = extract_document_graph(
        relpath="events.md",
        title="Events",
        body="Launch Window causes Support Load. Migration Window affects Billing API.",
        wiki_slug="events",
    )

    nodes_by_label = {node.label: node for node in result.nodes}
    assert nodes_by_label["Launch Window"].type == "Event"
    assert nodes_by_label["Migration Window"].type == "Event"


def test_tree_title_entity_uses_project_or_document_bias() -> None:
    body = "Atlas Initiative depends on Billing API."
    tree = PageTree(
        source_relpath="tree.md",
        source_format="md",
        doc_title="Tree",
        root_nodes=[
            TreeNode(
                node_id="n1",
                title="Atlas Initiative",
                level=2,
                start_offset=0,
                end_offset=len(body),
                children=[],
            )
        ],
        build_method="rule",
        built_at="2026-05-19T00:00:00Z",
        total_nodes=1,
        source_sha256="x",
    )

    result = extract_document_graph(
        relpath="tree.md",
        title="Tree",
        body=body,
        wiki_slug="tree",
        page_tree=tree,
    )

    relation_node = next(
        node
        for node in result.nodes
        if node.label == "Atlas Initiative" and not node.id.startswith("document:section-")
    )
    assert relation_node.type == "Project"


def test_multiple_depends_on_inbound_targets_use_concept() -> None:
    result = extract_document_graph(
        relpath="dependencies.md",
        title="Dependencies",
        body=(
            "Atlas depends on Release milestone. "
            "Borealis depends on Release milestone."
        ),
        wiki_slug="dependencies",
    )

    release_nodes = [node for node in result.nodes if node.label == "Release milestone"]
    assert len(release_nodes) == 1
    assert release_nodes[0].type == "Concept"
    assert sum(1 for edge in result.edges if edge.target == release_nodes[0].id) >= 2
