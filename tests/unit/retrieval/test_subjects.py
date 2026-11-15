from hks.retrieval.bm25 import CoverageScorer
from hks.retrieval.subjects import query_subject_text


def test_question_words_do_not_count_as_missing_subject_evidence() -> None:
    text = "Stock 素材的授權門檻"
    scorer = CoverageScorer("請問 Stock 素材的授權門檻是什麼？", [text])

    assert scorer.score(text) == 1.0
    assert scorer.score("unrelated deployment completed") == 0.0


def test_subject_keeps_uppercase_names_and_compound_identifiers() -> None:
    assert " ".join(query_subject_text("What is US policy for ERR-4012?").split()) == (
        "US policy ERR-4012?"
    )
    scorer = CoverageScorer("What does VID236 mean?", ["VID-236"])
    assert scorer.score("VID-236") == scorer.score("VID236")


def test_question_with_no_subject_is_not_measurable() -> None:
    assert not CoverageScorer("請問是什麼？", ["a record"]).measurable
