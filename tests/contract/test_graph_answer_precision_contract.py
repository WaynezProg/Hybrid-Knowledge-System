"""025：graph route 只以問句點名的實體、問句要的關係類型作答。"""

from __future__ import annotations

from pathlib import Path

from hks.core.paths import runtime_paths
from hks.graph.extract import extract_document_graph
from hks.graph.query import answer_query
from hks.graph.store import GraphStore

BODY = (
    "A 專案延遲會影響 checkout service 與 notification service。\n"
    "因為 checkout service 依賴 A 專案提供的 pricing API。\n"
    "Borealis affects Billing Service.\n"
)


def _store(root: Path) -> GraphStore:
    store = GraphStore(runtime_paths(root))
    store.replace_document(
        "dependency-map.md",
        extract_document_graph(
            relpath="dependency-map.md",
            title="Dependency Map",
            body=BODY,
            wiki_slug="dependency-map",
        ),
    )
    return store


def test_a_relation_word_alone_is_not_an_answer(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root)

    assert answer_query("What does the weather impact?", store) is None
    assert answer_query("天氣會影響什麼？", store) is None


def test_a_missing_relation_type_is_not_answered_with_another(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root)

    # The graph holds no ``owns`` edge; checkout service is in impacts / depends_on ones.
    assert answer_query("who owns checkout service", store) is None


def test_only_the_named_entity_is_listed(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root)

    result = answer_query("Borealis 影響哪個服務？", store)

    assert result is not None
    assert result.relations == ["impacts"]
    assert "Billing Service" in result.answer
    assert "checkout" not in result.answer and "A 專案" not in result.answer
    assert len(result.edge_ids) == 1
    assert result.confidence >= 0.9


def test_a_partly_named_entity_answers_with_less_confidence(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root)

    result = answer_query("哪些 service 受影響？", store)

    assert result is not None
    assert result.relations == ["impacts"]
    assert result.confidence == 0.8
