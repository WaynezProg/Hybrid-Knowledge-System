"""Unit tests for route-specific confidence assessment."""

from __future__ import annotations

from hks.retrieval.confidence import ConfidenceAssessment, assess


class TestAssessWiki:
    """Wiki auto writeback is always ineligible."""

    def test_wiki_high_confidence_still_ineligible(self) -> None:
        result = assess(
            route="wiki",
            raw_score=1.0,
            evidence=[
                {"source_relpath": "atlas.md", "route": "wiki", "quote": "Atlas summary"}
            ],
        )
        assert isinstance(result, ConfidenceAssessment)
        assert result.retrieval_score == 1.0
        assert result.writeback_eligible is False
        assert any("wiki" in reason.lower() for reason in result.reasons)

    def test_wiki_zero_confidence(self) -> None:
        result = assess(route="wiki", raw_score=0.0, evidence=[])
        assert result.writeback_eligible is False
        assert result.confidence == 0.0


class TestAssessGraph:
    """Graph auto writeback requires edge provenance, evidence, and threshold."""

    def test_graph_with_full_evidence_eligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"}],
            metadata={
                "edge_ids": ["e1"],
                "evidence_by_relpath": {"dep.md": "A impacts B"},
            },
        )
        assert result.writeback_eligible is True
        assert result.confidence >= 0.75

    def test_graph_missing_edge_ids_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"}],
            metadata={"evidence_by_relpath": {"dep.md": "A impacts B"}},
        )
        assert result.writeback_eligible is False
        assert any("edge" in reason.lower() for reason in result.reasons)

    def test_graph_missing_evidence_by_relpath_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"}],
            metadata={"edge_ids": ["e1"]},
        )
        assert result.writeback_eligible is False

    def test_graph_empty_evidence_list_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[],
            metadata={"edge_ids": ["e1"], "evidence_by_relpath": {"dep.md": "text"}},
        )
        assert result.writeback_eligible is False

    def test_graph_below_threshold_ineligible(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.3,
            evidence=[{"source_relpath": "dep.md", "route": "graph", "quote": "weak"}],
            metadata={"edge_ids": ["e1"], "evidence_by_relpath": {"dep.md": "weak"}},
        )
        assert result.writeback_eligible is False

    def test_graph_later_writeback_source_relpath_is_invalid_provenance(self) -> None:
        result = assess(
            route="graph",
            raw_score=0.88,
            evidence=[
                {"source_relpath": "dep.md", "route": "graph", "quote": "A impacts B"},
                {
                    "source_relpath": "<writeback>",
                    "route": "graph",
                    "quote": "generated edge",
                },
            ],
            metadata={
                "edge_ids": ["e1"],
                "evidence_by_relpath": {"dep.md": "A impacts B"},
            },
        )
        assert result.writeback_eligible is False
        assert any("<writeback>" in reason for reason in result.reasons)


class TestAssessVector:
    """Vector auto writeback requires source, quote, evidence, and threshold."""

    def test_vector_with_full_evidence_eligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "fact text"}],
        )
        assert result.writeback_eligible is True

    def test_vector_missing_source_relpath_ineligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"route": "vector", "quote": "fact text"}],
        )
        assert result.writeback_eligible is False

    def test_vector_missing_quote_ineligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"source_relpath": "a.md", "route": "vector"}],
        )
        assert result.writeback_eligible is False

    def test_vector_below_similarity_threshold_ineligible(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.3,
            evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "low sim"}],
        )
        assert result.writeback_eligible is False

    def test_vector_empty_evidence_ineligible(self) -> None:
        result = assess(route="vector", raw_score=0.9, evidence=[])
        assert result.writeback_eligible is False

    def test_vector_writeback_source_relpath_is_invalid_provenance(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[
                {"source_relpath": "<writeback>", "route": "vector", "quote": "generated text"}
            ],
        )
        assert result.writeback_eligible is False
        assert any("<writeback>" in reason for reason in result.reasons)

    def test_vector_later_writeback_source_relpath_is_invalid_provenance(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[
                {"source_relpath": "a.md", "route": "vector", "quote": "fact text"},
                {"source_relpath": "<writeback>", "route": "vector", "quote": "generated text"},
            ],
        )
        assert result.writeback_eligible is False
        assert any("<writeback>" in reason for reason in result.reasons)


class TestAssessPageTree:
    """Page tree auto writeback requires section provenance."""

    def test_page_tree_with_full_evidence_eligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "section content",
                    "section_path": "Chapter 1 > Intro",
                    "page_range": {"start": 1, "end": 3},
                }
            ],
        )
        assert result.writeback_eligible is True

    def test_page_tree_missing_section_path_ineligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "content",
                    "page_range": {"start": 1, "end": 3},
                }
            ],
        )
        assert result.writeback_eligible is False

    def test_page_tree_missing_page_range_ineligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "content",
                    "section_path": "Chapter 1",
                }
            ],
        )
        assert result.writeback_eligible is False

    def test_page_tree_empty_quote_ineligible(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "",
                    "section_path": "Ch1",
                    "page_range": {"start": 1, "end": 2},
                }
            ],
        )
        assert result.writeback_eligible is False

    def test_page_tree_later_writeback_source_relpath_is_invalid_provenance(self) -> None:
        result = assess(
            route="page_tree",
            raw_score=0.7,
            evidence=[
                {
                    "source_relpath": "doc.pdf",
                    "route": "page_tree",
                    "quote": "section content",
                    "section_path": "Chapter 1 > Intro",
                    "page_range": {"start": 1, "end": 3},
                },
                {
                    "source_relpath": "<writeback>",
                    "route": "page_tree",
                    "quote": "generated section",
                    "section_path": "Chapter 2 > Generated",
                    "page_range": {"start": 4, "end": 5},
                },
            ],
        )
        assert result.writeback_eligible is False
        assert any("<writeback>" in reason for reason in result.reasons)


class TestAssessConfidence:
    """Confidence is clamped [0.0, 1.0]."""

    def test_confidence_equals_raw_for_initial_release(self) -> None:
        result = assess(
            route="vector",
            raw_score=0.85,
            evidence=[{"source_relpath": "a.md", "route": "vector", "quote": "text"}],
        )
        assert result.confidence == result.retrieval_score

    def test_confidence_clamped_at_zero(self) -> None:
        result = assess(route="wiki", raw_score=-0.5, evidence=[])
        assert result.confidence == 0.0

    def test_confidence_clamped_at_one(self) -> None:
        result = assess(route="wiki", raw_score=1.5, evidence=[])
        assert result.confidence == 1.0

    def test_retrieval_score_equals_raw_score(self) -> None:
        result = assess(route="vector", raw_score=0.42, evidence=[])
        assert result.retrieval_score == 0.42
