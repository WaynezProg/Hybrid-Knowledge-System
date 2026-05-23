"""Session-memory daily-source candidate retrieval."""

from __future__ import annotations

from hks.core.schema import TraceStep
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.routing.session_memory import (
    SessionMemoryIntent,
    metadata_matches_session_intent,
)
from hks.storage.wiki import WikiPage, WikiStore


def collect_session_memory_candidates(
    question: str,
    *,
    wiki_store: WikiStore,
    intent: SessionMemoryIntent | None,
) -> tuple[list[Candidate], list[TraceStep]]:
    if intent is None:
        return [], []

    candidates: list[Candidate] = []
    for page in wiki_store.list_pages():
        metadata: dict[str, object] = {
            **page.metadata,
            "source_relpath": page.source_relpath,
        }
        if not metadata_matches_session_intent(metadata, intent):
            continue
        text = _answer_text(page)
        quote = evidence_quote(text)
        candidates.append(
            Candidate(
                text=text,
                source_route="wiki",
                score=1.0,
                metadata={
                    **metadata,
                    "slug": page.slug,
                    "quote": quote,
                    "session_memory_intent": True,
                },
            )
        )

    if candidates:
        candidates.sort(key=lambda candidate: str(candidate.metadata.get("source_relpath")))
        return candidates, [
            TraceStep(
                kind="wiki_lookup",
                detail={
                    "hit": True,
                    "mode": "session_memory",
                    "intent": intent.to_detail(),
                    "candidate_count": len(candidates),
                    "source_relpath": candidates[0].metadata.get("source_relpath"),
                    "quote": candidates[0].metadata.get("quote"),
                },
            )
        ]

    return [], [
        TraceStep(
            kind="wiki_lookup",
            detail={
                "hit": False,
                "mode": "session_memory",
                "intent": intent.to_detail(),
            },
        )
    ]


def prefer_session_memory_candidates(
    candidates: list[Candidate],
    intent: SessionMemoryIntent | None,
) -> tuple[list[Candidate], int]:
    if intent is None:
        return candidates, 0
    preferred = [
        candidate
        for candidate in candidates
        if metadata_matches_session_intent(candidate.metadata, intent)
    ]
    if not preferred:
        return candidates, 0
    return preferred, len(preferred)


def _answer_text(page: WikiPage) -> str:
    body = page.body.strip()
    if body:
        return body
    return f"{page.title}: {page.summary}"
