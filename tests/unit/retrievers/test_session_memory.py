from __future__ import annotations

from hks.retrieval.evidence import candidate_evidence
from hks.retrieval.models import Candidate
from hks.retrievers.session_memory import (
    prefer_session_memory_candidates,
    synthesize_workspace_status,
)
from hks.routing.session_memory import SessionMemoryIntent


def _make_candidate(
    text: str,
    route: str = "vector",
    score: float = 0.6,
    **meta: object,
) -> Candidate:
    return Candidate(text=text, source_route=route, score=score, metadata=dict(meta))


class TestPreferSessionMemoryCandidatesWorkspace:
    def test_filters_to_workspace_matched_candidates(self) -> None:
        intent = SessionMemoryIntent(workspace="social-bank-check")
        candidates = [
            _make_candidate(
                "wiki page summary",
                route="wiki",
                score=1.0,
                source_relpath="daily/2026-05-21.md",
                slug="2026-05-21",
            ),
            _make_candidate(
                "pytest 4 passed",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-21",
            ),
            _make_candidate(
                "HKS test run",
                workspace_id="hks-81c05951",
                date="2026-05-21",
            ),
        ]

        preferred, count = prefer_session_memory_candidates(candidates, intent)

        assert count == 1
        assert len(preferred) == 1
        assert preferred[0].text == "pytest 4 passed"

    def test_falls_back_when_no_workspace_match(self) -> None:
        intent = SessionMemoryIntent(workspace="nonexistent-ws")
        candidates = [
            _make_candidate("wiki page", route="wiki", score=1.0),
            _make_candidate("vector hit", workspace_id="hks-81c05951"),
        ]

        preferred, count = prefer_session_memory_candidates(candidates, intent)

        assert count == 0
        assert len(preferred) == 2

    def test_none_intent_returns_all(self) -> None:
        candidates = [
            _make_candidate("a"),
            _make_candidate("b"),
        ]

        preferred, count = prefer_session_memory_candidates(candidates, None)

        assert count == 0
        assert len(preferred) == 2


class TestSynthesizeWorkspaceStatus:
    def test_synthesizes_multiple_entries(self) -> None:
        intent = SessionMemoryIntent(
            workspace="social-bank-check",
            is_status_query=True,
        )
        candidates = [
            _make_candidate(
                "pytest 4 passed",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-21",
                source_relpath="daily/2026-05-21.md",
                score=0.7,
            ),
            _make_candidate(
                "pytest 8 passed",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-21",
                source_relpath="daily/2026-05-21.md",
                score=0.6,
            ),
        ]

        result = synthesize_workspace_status(candidates, intent)

        assert result is not None
        assert "social-bank-check" in result.text
        assert "2026-05-21" in result.text
        assert "pytest 4 passed" in result.text
        assert "pytest 8 passed" in result.text
        assert result.metadata["entry_count"] == 2
        assert result.metadata["latest_date"] == "2026-05-21"
        assert result.metadata["synthesized"] is True
        assert result.score == 0.7

    def test_sorts_by_date_descending(self) -> None:
        intent = SessionMemoryIntent(
            workspace="social-bank-check",
            is_status_query=True,
        )
        candidates = [
            _make_candidate(
                "old entry",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-20",
            ),
            _make_candidate(
                "new entry",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-21",
            ),
        ]

        result = synthesize_workspace_status(candidates, intent)

        assert result is not None
        assert result.metadata["latest_date"] == "2026-05-21"
        new_pos = result.text.index("new entry")
        old_pos = result.text.index("old entry")
        assert new_pos < old_pos

    def test_keeps_evidence_for_each_source_file_in_latest_first_order(self) -> None:
        intent = SessionMemoryIntent(
            workspace="social-bank-check",
            is_status_query=True,
        )
        candidates = [
            _make_candidate(
                "old entry",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-20",
                source_relpath="daily/2026-05-20.md",
            ),
            _make_candidate(
                "new entry",
                workspace_id="social-bank-check-d61a68f0",
                date="2026-05-21",
                source_relpath="daily/2026-05-21.md",
            ),
        ]

        result = synthesize_workspace_status(candidates, intent)

        assert result is not None
        assert result.metadata["source_relpath"] == "daily/2026-05-21.md"
        assert [item["source_relpath"] for item in candidate_evidence(result)] == [
            "daily/2026-05-21.md",
            "daily/2026-05-20.md",
        ]

    def test_filters_unmatched_workspace(self) -> None:
        intent = SessionMemoryIntent(
            workspace="social-bank-check",
            is_status_query=True,
        )
        candidates = [
            _make_candidate(
                "wrong workspace",
                workspace_id="hks-81c05951",
                date="2026-05-21",
            ),
        ]

        result = synthesize_workspace_status(candidates, intent)

        assert result is None

    def test_returns_none_for_empty_candidates(self) -> None:
        intent = SessionMemoryIntent(
            workspace="social-bank-check",
            is_status_query=True,
        )

        result = synthesize_workspace_status([], intent)

        assert result is None

    def test_returns_none_without_workspace(self) -> None:
        intent = SessionMemoryIntent(date="2026-05-21")

        result = synthesize_workspace_status(
            [_make_candidate("entry", workspace_id="hks-81c05951")],
            intent,
        )

        assert result is None
