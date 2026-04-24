"""Persist query answers back into the wiki store."""

from __future__ import annotations

from hks.core.schema import QueryResponse, TraceStep
from hks.storage.wiki import LogEntry, WikiStore


def commit(
    *,
    query: str,
    response: QueryResponse,
    wiki_store: WikiStore | None = None,
) -> list[TraceStep]:
    store = wiki_store or WikiStore()
    page = store.write_page(
        title=query.strip(),
        summary=response.answer.strip().replace("\n", " ")[:80],
        body=f"# {query.strip()}\n\n{response.answer.strip()}",
        source_relpath="<writeback>",
        origin="writeback",
    )
    store.append_log(
        LogEntry(
            timestamp=page.updated_at,
            event="writeback",
            status="committed",
            query=query,
            route=response.trace.route,
            source=response.source,
            pages_touched=[f"pages/{page.slug}.md"],
            confidence=response.confidence,
        )
    )
    return [
        TraceStep(
            kind="writeback",
            detail={
                "status": "committed",
                "slug": page.slug,
                "path": f"pages/{page.slug}.md",
            },
        )
    ]
