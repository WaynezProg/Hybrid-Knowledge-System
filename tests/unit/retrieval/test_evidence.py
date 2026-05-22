"""Unit tests for candidate evidence generation."""

from __future__ import annotations

from hks.retrieval.evidence import candidate_evidence, evidence_quote
from hks.retrieval.models import Candidate


def test_evidence_quote_normalizes_whitespace_and_caps_length() -> None:
    text = "  alpha\n\n beta   gamma  "
    assert evidence_quote(text, limit=12) == "alpha beta g"


def test_wiki_candidate_evidence_uses_source_relpath_and_quote_metadata() -> None:
    candidate = Candidate(
        text="Atlas summary",
        source_route="wiki",
        score=1.0,
        metadata={
            "source_relpath": "project-atlas.txt",
            "quote": "Project Atlas 目前處於設計收斂階段。",
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "project-atlas.txt",
            "route": "wiki",
            "quote": "Project Atlas 目前處於設計收斂階段。",
        }
    ]


def test_graph_candidate_evidence_uses_edge_quotes_per_relpath() -> None:
    candidate = Candidate(
        text="Atlas 會影響 Billing API",
        source_route="graph",
        score=0.88,
        metadata={
            "relpaths": ["dependency-map.md"],
            "evidence_by_relpath": {
                "dependency-map.md": "Project Atlas affects Billing API."
            },
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "dependency-map.md",
            "route": "graph",
            "quote": "Project Atlas affects Billing API.",
        }
    ]


def test_vector_candidate_evidence_includes_winning_quote_and_location() -> None:
    candidate = Candidate(
        text="clause 7.4 requires risk controls before launch.",
        source_route="vector",
        score=0.91,
        metadata={
            "source_relpath": "reports/launch-plan.md",
            "section_path": "Launch Plan > Risk Controls",
            "page_range": {"start": 4, "end": 6},
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "reports/launch-plan.md",
            "route": "vector",
            "section_path": "Launch Plan > Risk Controls",
            "page_range": {"start": 4, "end": 6},
            "quote": "clause 7.4 requires risk controls before launch.",
        }
    ]


def test_page_tree_candidate_evidence_includes_section_path_and_page_range() -> None:
    candidate = Candidate(
        text="Nebula arbitration requires coordinator approval.",
        source_route="page_tree",
        score=0.6,
        metadata={
            "source_relpath": "project-atlas.txt",
            "section_path": "Nebula Arbitration",
            "page_range": {"start": 12, "end": 14},
        },
    )

    assert candidate_evidence(candidate) == [
        {
            "source_relpath": "project-atlas.txt",
            "route": "page_tree",
            "quote": "Nebula arbitration requires coordinator approval.",
            "section_path": "Nebula Arbitration",
            "page_range": {"start": 12, "end": 14},
        }
    ]
