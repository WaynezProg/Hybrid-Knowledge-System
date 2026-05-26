"""Session-memory daily-source candidate retrieval."""

from __future__ import annotations

from hks.core.schema import TraceStep
from hks.retrieval.evidence import evidence_quote
from hks.retrieval.models import Candidate
from hks.routing.session_memory import (
    SessionMemoryIntent,
    metadata_matches_session_intent,
    workspace_id_matches,
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


def synthesize_workspace_status(
    candidates: list[Candidate],
    intent: SessionMemoryIntent,
) -> Candidate | None:
    if not intent.workspace or not candidates:
        return None

    matched = [
        c for c in candidates
        if workspace_id_matches(
            str(c.metadata.get("workspace_id") or ""),
            intent.workspace,
        )
    ]
    if not matched:
        return None

    matched.sort(
        key=lambda c: str(c.metadata.get("date") or ""),
        reverse=True,
    )

    latest_date = str(matched[0].metadata.get("date") or "unknown")
    workspace_display = intent.workspace

    lines: list[str] = [f"## {workspace_display} workspace 狀態", ""]
    lines.append(f"最近活動日期：{latest_date}")
    lines.append("")

    current_date = ""
    for candidate in matched:
        entry_date = str(candidate.metadata.get("date") or "unknown")
        if entry_date != current_date:
            current_date = entry_date
            lines.append(f"### {current_date}")

        text = candidate.text.strip()
        if text:
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    lines.append(f"- {stripped}" if not stripped.startswith("-") else stripped)
        lines.append("")

    merged_meta: dict[str, object] = {
        "workspace": workspace_display,
        "latest_date": latest_date,
        "entry_count": len(matched),
        "synthesized": True,
    }
    source_relpaths: list[str] = []
    evidence_text_by_relpath: dict[str, list[str]] = {}
    route_by_relpath: dict[str, str] = {}
    for candidate in matched:
        relpath = str(candidate.metadata.get("source_relpath") or "")
        if not relpath:
            continue
        if relpath not in evidence_text_by_relpath:
            source_relpaths.append(relpath)
            evidence_text_by_relpath[relpath] = []
            route_by_relpath[relpath] = candidate.source_route
        evidence_text_by_relpath[relpath].append(candidate.text)

    if source_relpaths:
        merged_meta["source_relpaths"] = source_relpaths
        merged_meta["source_relpath"] = source_relpaths[0]
        merged_meta["_hks_evidence_items"] = [
            {
                "source_relpath": relpath,
                "route": route_by_relpath[relpath],
                "quote": evidence_quote("\n".join(evidence_text_by_relpath[relpath])),
            }
            for relpath in source_relpaths
        ]

    quote = evidence_quote("\n".join(lines))

    best_score = max(c.score for c in matched)
    merged_meta["quote"] = quote

    return Candidate(
        text="\n".join(lines),
        source_route=matched[0].source_route,
        score=best_score,
        metadata=merged_meta,
    )


def _answer_text(page: WikiPage) -> str:
    body = page.body.strip()
    if body:
        return body
    return f"{page.title}: {page.summary}"
