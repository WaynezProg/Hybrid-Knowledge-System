"""Unit tests for evidence auto-aggregation from trace steps."""

from __future__ import annotations

from hks.core.schema import QueryResponse, Trace, TraceStep


class TestEvidenceAggregation:
    def test_wiki_hit_produces_evidence(self) -> None:
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
        )

        payload = response.to_dict()

        assert "evidence" in payload
        assert len(payload["evidence"]) == 1
        assert payload["evidence"][0]["source_relpath"] == "atlas.md"
        assert payload["evidence"][0]["route"] == "wiki"

    def test_graph_hit_expands_relpaths(self) -> None:
        response = QueryResponse(
            answer="graph answer",
            source=["graph"],
            confidence=0.88,
            trace=Trace(
                route="graph",
                steps=[
                    TraceStep(
                        kind="graph_lookup",
                        detail={
                            "hit": True,
                            "relpaths": ["dep-map.md", "impact.pdf"],
                            "node_ids": ["n1"],
                            "edge_ids": ["e1"],
                            "relations": ["impacts"],
                        },
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert len(payload["evidence"]) == 2
        relpaths = [e["source_relpath"] for e in payload["evidence"]]
        assert "dep-map.md" in relpaths
        assert "impact.pdf" in relpaths
        assert all(e["route"] == "graph" for e in payload["evidence"])

    def test_vector_hit_includes_section_and_page(self) -> None:
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
                            "section_path": "Chapter 1 > Methods",
                            "page_range": {"start": 3, "end": 5},
                        },
                    )
                ],
            ),
        )

        payload = response.to_dict()

        assert len(payload["evidence"]) == 1
        ev = payload["evidence"][0]
        assert ev["source_relpath"] == "report.pdf"
        assert ev["section_path"] == "Chapter 1 > Methods"
        assert ev["page_range"] == {"start": 3, "end": 5}
        assert ev["route"] == "vector"

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

    def test_dedupes_by_relpath_and_route(self) -> None:
        response = QueryResponse(
            answer="combined",
            source=["wiki", "vector"],
            confidence=0.9,
            trace=Trace(
                route="wiki",
                steps=[
                    TraceStep(
                        kind="wiki_lookup",
                        detail={"hit": True, "source_relpath": "atlas.md"},
                    ),
                    TraceStep(
                        kind="vector_lookup",
                        detail={
                            "top_k": 5,
                            "top_similarity": 0.8,
                            "source_relpath": "atlas.md",
                        },
                    ),
                ],
            ),
        )

        payload = response.to_dict()

        assert len(payload["evidence"]) == 2
        routes = {e["route"] for e in payload["evidence"]}
        assert routes == {"wiki", "vector"}
