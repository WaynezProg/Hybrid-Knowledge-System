"""025：graph route 只以問句點名的實體、問句要的關係類型作答。"""

from __future__ import annotations

from pathlib import Path

from hks.core.paths import runtime_paths
from hks.graph.extract import extract_document_graph
from hks.graph.query import answer_query
from hks.graph.store import GraphStore
from hks.retrieval.confidence import assess

BODY = (
    "A 專案延遲會影響 checkout service 與 notification service。\n"
    "因為 checkout service 依賴 A 專案提供的 pricing API。\n"
    "Borealis affects Billing Service.\n"
)


def _store(root: Path, body: str = BODY) -> GraphStore:
    store = GraphStore(runtime_paths(root))
    store.replace_document(
        "dependency-map.md",
        extract_document_graph(
            relpath="dependency-map.md",
            title="Dependency Map",
            body=body,
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


def test_one_shared_word_answers_below_the_write_back_threshold(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root)

    result = answer_query("哪些 service 受影響？", store)

    assert result is not None
    assert result.relations == ["impacts"]
    assert result.confidence == 0.7
    assert not assess(
        route="graph",
        raw_score=result.confidence,
        evidence=[{"source_relpath": "dependency-map.md"}],
        metadata={"edge_ids": result.edge_ids, "evidence_by_relpath": {"dependency-map.md": "x"}},
    ).writeback_eligible


def test_two_words_in_a_row_of_a_label_name_it(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root, "Project A delay affects checkout service.\n")

    named = answer_query("Which services are affected if Project A slips", store)
    other = answer_query("What does Project Z impact?", store)

    assert named is not None and named.confidence >= 0.9
    assert other is not None and other.confidence == 0.7


def test_both_entities_written_in_full_are_answered(tmp_ks_root: Path) -> None:
    store = _store(
        tmp_ks_root,
        "Atlas affects Checkout.\nATLAS affects Checkout.\nBorealis affects Billing.\n",
    )

    result = answer_query("What do Atlas and Borealis affect?", store)

    assert result is not None
    assert "Atlas" in result.answer and "Borealis" in result.answer


def test_a_name_inside_another_word_is_not_named(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root, "Ann owns Atlas.\n")

    assert answer_query("Who owns the planning?", store) is None
    assert answer_query("What does Ann own?", store) is not None


def test_a_cjk_name_is_found_wherever_the_sentence_starts(tmp_ks_root: Path) -> None:
    store = _store(tmp_ks_root, "資料庫故障影響 Checkout。\n")

    assert answer_query("資料庫出問題會影響什麼？", store) is not None
    assert answer_query("因資料庫出問題會影響什麼？", store) is not None
