"""Unit tests for query response evidence serialization."""

from __future__ import annotations

from hks.core.schema import QueryResponse, Trace, TraceStep


class TestEvidenceSerialization:
    def test_explicit_evidence_is_serialized(self) -> None:
        response = QueryResponse(
            answer="Atlas summary",
            source=["wiki"],
            confidence=1.0,
            trace=Trace(
                route="wiki",
                steps=[
                    TraceStep(
                        kind="wiki_lookup",
                        detail={
                            "slug": "atlas",
                            "hit": True,
                            "source_relpath": "atlas.md",
                        },
                    )
                ],
            ),
            evidence=[
                {
                    "source_relpath": "atlas.md",
                    "route": "wiki",
                    "quote": "Atlas project summary",
                }
            ],
        )

        payload = response.to_dict()

        assert payload["evidence"] == [
            {
                "source_relpath": "atlas.md",
                "route": "wiki",
                "quote": "Atlas project summary",
            }
        ]

    def test_trace_steps_do_not_create_uncited_evidence(self) -> None:
        response = QueryResponse(
            answer="Atlas summary",
            source=["wiki"],
            confidence=1.0,
            trace=Trace(
                route="wiki",
                steps=[
                    TraceStep(
                        kind="wiki_lookup",
                        detail={
                            "slug": "atlas",
                            "hit": True,
                            "source_relpath": "atlas.md",
                        },
                    ),
                    TraceStep(
                        kind="vector_lookup",
                        detail={
                            "top_k": 5,
                            "top_similarity": 0.8,
                            "source_relpath": "atlas.md",
                            "quote": "Vector candidate that did not win",
                        },
                    ),
                ],
            ),
        )

        payload = response.to_dict()

        assert "evidence" not in payload

    def test_no_hit_omits_evidence(self) -> None:
        response = QueryResponse(
            answer="not found",
            source=[],
            confidence=0.0,
            trace=Trace(
                route="vector",
                steps=[
                    TraceStep(
                        kind="vector_lookup",
                        detail={"top_k": 5, "top_similarity": 0.1},
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert "evidence" not in payload

    def test_explicit_vector_evidence_includes_section_page_and_quote(self) -> None:
        response = QueryResponse(
            answer="vector text",
            source=["vector"],
            confidence=0.75,
            trace=Trace(
                route="vector",
                steps=[
                    TraceStep(
                        kind="vector_lookup",
                        detail={
                            "top_k": 5,
                            "top_similarity": 0.8,
                            "source_relpath": "report.pdf",
                        },
                    )
                ],
            ),
            evidence=[
                {
                    "source_relpath": "report.pdf",
                    "route": "vector",
                    "section_path": "Chapter 1 > Methods",
                    "page_range": {"start": 3, "end": 5},
                    "quote": "clause 7.4 requires risk controls before launch.",
                }
            ],
        )

        payload = response.to_dict()

        assert payload["evidence"] == [
            {
                "source_relpath": "report.pdf",
                "route": "vector",
                "section_path": "Chapter 1 > Methods",
                "page_range": {"start": 3, "end": 5},
                "quote": "clause 7.4 requires risk controls before launch.",
            }
        ]
