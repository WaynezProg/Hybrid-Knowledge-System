"""Edge-case tests for heuristic graph extraction."""

from __future__ import annotations

from hks.graph.extract import extract_document_graph
from hks.graph.store import GraphDocumentArtifacts


def _extract(body: str) -> GraphDocumentArtifacts:
    return extract_document_graph(
        relpath="doc.md",
        title="Doc",
        body=body,
        wiki_slug="doc",
    )


def _labels_for_relation(result: GraphDocumentArtifacts, relation: str) -> set[tuple[str, str]]:
    nodes = {node.id: node.label for node in result.nodes}
    return {
        (nodes[edge.source], nodes[edge.target])
        for edge in result.edges
        if edge.relation == relation
    }


def test_comma_separated_targets_extract_each_target_without_conjunction_prefix() -> None:
    result = _extract("A impacts B, C, and D.")

    assert _labels_for_relation(result, "impacts") == {
        ("A", "B"),
        ("A", "C"),
        ("A", "D"),
    }


def test_nested_entity_names_remain_single_labels() -> None:
    result = _extract("Project Atlas Phase 2 impacts Billing API.")

    assert ("Project Atlas Phase 2", "Billing API") in _labels_for_relation(
        result,
        "impacts",
    )


def test_leading_or_in_source_label_is_preserved() -> None:
    result = _extract("Or Platform impacts Billing API.")

    assert ("Or Platform", "Billing API") in _labels_for_relation(result, "impacts")


def test_empty_body_only_creates_document_node() -> None:
    result = _extract("")

    assert [node.label for node in result.nodes] == ["Doc"]
    assert result.edges == []


def test_chinese_text_without_relation_pattern_does_not_create_edges() -> None:
    result = _extract("這是一段只有中文的描述，沒有明確關係。")

    assert [node.label for node in result.nodes] == ["Doc"]
    assert result.edges == []


def test_english_text_without_relation_pattern_does_not_create_edges() -> None:
    result = _extract("This is English prose without an explicit graph relation.")

    assert [node.label for node in result.nodes] == ["Doc"]
    assert result.edges == []
