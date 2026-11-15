"""Promote approved writeback review queue items into evidence-backed wiki pages."""

from __future__ import annotations

from hks.core.lock import file_lock
from hks.core.manifest import load_manifest
from hks.core.schema import TraceStep
from hks.errors import ExitCode, KSError
from hks.storage.wiki import LogEntry, WikiPage, WikiStore
from hks.writeback.queue import WritebackQueueItem

WRITEBACK_PLACEHOLDER_SOURCE = "<writeback>"


def valid_evidence_items(item: WritebackQueueItem) -> list[dict[str, str]]:
    """Evidence that names a source and quotes it; the `<writeback>` placeholder never counts."""
    valid: list[dict[str, str]] = []
    for evidence in item.evidence:
        source_relpath = evidence.get("source_relpath")
        quote = evidence.get("quote")
        if not isinstance(source_relpath, str) or not source_relpath.strip():
            continue
        source = source_relpath.strip()
        if source == WRITEBACK_PLACEHOLDER_SOURCE:
            continue
        if not isinstance(quote, str) or not quote.strip():
            continue
        valid.append(
            {
                "source_relpath": source,
                "quote": " ".join(quote.split()),
            }
        )
    return valid


def promote(
    *,
    item: WritebackQueueItem,
    wiki_store: WikiStore | None = None,
) -> list[TraceStep]:
    """Write the wiki page for an approved item. The only writeback path into the wiki.

    Holds the shared runtime write lock (`paths.lock`) that ingest, lint fix and wiki
    synthesis apply also hold, so the slug check, the page, the index and the log entry
    cannot interleave with them. A caller that also holds a queue item lock takes that
    one first; nothing else takes the two in the other order.
    """
    store = wiki_store or WikiStore()
    with file_lock(store.paths.lock):
        evidence_items = _source_backed_evidence_items(store, valid_evidence_items(item))
        if not evidence_items:
            raise KSError(
                "writeback approval 需要至少一筆真實來源 evidence",
                exit_code=ExitCode.DATAERR,
                code="WRITEBACK_EVIDENCE_REQUIRED",
                hint="reject this item, or re-run the query to enqueue one with source evidence",
            )

        question = item.question.strip()
        answer = item.answer.strip()
        target_slug = store.slug_base(question)
        _ensure_promotable_slug(store, target_slug)
        related_pages = _related_pages(
            store,
            source_relpaths=[evidence["source_relpath"] for evidence in evidence_items],
            exclude_slug=target_slug,
        )
        body = [f"# {question}", "", answer, "", "## 來源依據", ""]
        body.extend(
            f'- {evidence["source_relpath"]} — "{evidence["quote"]}"'
            for evidence in evidence_items
        )
        if related_pages:
            body.extend(["", "## Related", ""])
            body.extend(
                f"- [{WikiStore._escape_link_text(page.title)}]({page.slug}.md)"
                for page in related_pages
            )
        page = store.write_page(
            title=question,
            summary=answer.replace("\n", " ")[:80],
            body="\n".join(body),
            source_relpath=evidence_items[0]["source_relpath"],
            origin="writeback",
            preferred_slug=target_slug,
            metadata={"writeback_query": question},
        )
        store.append_log(
            LogEntry(
                timestamp=page.updated_at,
                event="writeback",
                status="approved",
                query=question,
                route=item.route,
                source=item.source,
                pages_touched=[f"pages/{page.slug}.md"],
                confidence=item.retrieval_score,
            )
        )
        detail: dict[str, object] = {
            "status": "approved",
            "slug": page.slug,
            "path": f"pages/{page.slug}.md",
            "source_relpath": page.source_relpath,
            "related": [related.slug for related in related_pages],
        }
        return [TraceStep(kind="writeback", detail=detail)]


def _source_backed_evidence_items(
    store: WikiStore,
    evidence_items: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Keep the evidence whose source is still ingested: in the manifest and on disk."""
    if not evidence_items:
        return []
    manifest = load_manifest(store.paths.manifest)
    backed: list[dict[str, str]] = []
    for evidence in evidence_items:
        source_relpath = evidence["source_relpath"]
        raw_source = store.paths.raw_sources / source_relpath
        if source_relpath in manifest.entries and raw_source.is_file():
            backed.append(evidence)
    return backed


def _ensure_promotable_slug(store: WikiStore, slug: str) -> None:
    page_path = store.paths.wiki_pages / f"{slug}.md"
    if not page_path.exists():
        return
    existing = store.load_page(slug)
    if existing.origin == "ingest":
        raise KSError(
            f"wiki page slug `{slug}` already exists from ingest",
            exit_code=ExitCode.DATAERR,
            code="CONFLICT",
            details=[f"pages/{slug}.md"],
            hint="reject this item; an ingested page already owns this slug",
        )


def _related_pages(
    store: WikiStore,
    *,
    source_relpaths: list[str],
    exclude_slug: str,
) -> list[WikiPage]:
    pages: list[WikiPage] = []
    seen: set[str] = set()
    for page in store.pages_for_source_relpaths(source_relpaths):
        if page.slug != exclude_slug and page.slug not in seen:
            pages.append(page)
            seen.add(page.slug)
    return pages
