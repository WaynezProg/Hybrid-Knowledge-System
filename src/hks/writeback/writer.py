"""Persist query answers back into the wiki store."""

from __future__ import annotations

from dataclasses import dataclass, field

from hks.core.schema import QueryResponse, TraceStep
from hks.storage.wiki import EventStatus, LogEntry, WikiPage, WikiStore


@dataclass(slots=True)
class WritebackContext:
    related_slugs: list[str] = field(default_factory=list)


def commit(
    *,
    query: str,
    response: QueryResponse,
    status: EventStatus = "committed",
    context: WritebackContext | None = None,
    wiki_store: WikiStore | None = None,
) -> list[TraceStep]:
    store = wiki_store or WikiStore()
    related_pages = _related_pages(store, context)
    body = [f"# {query.strip()}", "", response.answer.strip()]
    if related_pages:
        body.extend(["", "## Related", ""])
        body.extend(f"- [{page.title}]({page.slug}.md)" for page in related_pages)
    page = store.write_page(
        title=query.strip(),
        summary=response.answer.strip().replace("\n", " ")[:80],
        body="\n".join(body),
        source_relpath="<writeback>",
        origin="writeback",
    )
    store.append_log(
        LogEntry(
            timestamp=page.updated_at,
            event="writeback",
            status=status,
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
                "status": status,
                "slug": page.slug,
                "path": f"pages/{page.slug}.md",
                "related": [related.slug for related in related_pages],
            },
        )
    ]


def _related_pages(store: WikiStore, context: WritebackContext | None) -> list[WikiPage]:
    if context is None or not context.related_slugs:
        return []
    pages: list[WikiPage] = []
    for slug in context.related_slugs:
        try:
            pages.append(store.load_page(slug))
        except FileNotFoundError:
            continue
    return pages
