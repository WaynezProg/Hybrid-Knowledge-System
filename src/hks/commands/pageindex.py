"""Command wrappers for PageIndex tree operations."""

from __future__ import annotations

from hks.core.manifest import resume_or_rebuild
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Route, Trace, TraceStep
from hks.page_tree.enrich import enrich_tree
from hks.page_tree.store import TreeStore


def _summary_response(
    *,
    answer: str,
    source: list[Route],
    confidence: float,
    detail: dict[str, object],
) -> QueryResponse:
    return QueryResponse(
        answer=answer,
        source=source,
        confidence=confidence,
        trace=Trace(route="wiki", steps=[TraceStep(kind="pageindex_summary", detail=detail)]),
    )


def run_show(*, source_relpath: str) -> QueryResponse:
    paths = runtime_paths()
    store = TreeStore(paths)
    manifest = resume_or_rebuild(paths)
    entry = manifest.entries.get(source_relpath)
    if entry is None or entry.derived.page_tree is None:
        return _summary_response(
            answer=f"找不到 {source_relpath} 的 page tree",
            source=[],
            confidence=0.0,
            detail={"found": False, "source_relpath": source_relpath},
        )

    tree = store.load(entry.derived.page_tree)
    detail: dict[str, object] = {
        "found": True,
        "source_relpath": source_relpath,
        "tree_slug": entry.derived.page_tree,
        "tree": tree.to_dict(),
    }
    return _summary_response(
        answer=(
            f"page tree for {source_relpath}: "
            f"{tree.total_nodes} nodes, build_method={tree.build_method}"
        ),
        source=["wiki"],
        confidence=1.0,
        detail=detail,
    )


def run_enrich(
    *,
    source_relpath: str | None = None,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    force: bool = False,
) -> QueryResponse:
    paths = runtime_paths()
    store = TreeStore(paths)
    manifest = resume_or_rebuild(paths)

    targets = (
        [source_relpath]
        if source_relpath is not None
        else [
            relpath
            for relpath, entry in sorted(manifest.entries.items())
            if entry.derived.page_tree is not None
        ]
    )

    enriched_count = 0
    skipped_count = 0
    written: list[str] = []

    for relpath in targets:
        entry = manifest.entries.get(relpath)
        if entry is None or entry.derived.page_tree is None:
            skipped_count += 1
            continue

        tree = store.load(entry.derived.page_tree)
        raw_path = paths.raw_sources / relpath
        source_text = (
            raw_path.read_text(encoding="utf-8", errors="replace")
            if raw_path.exists()
            else ""
        )
        enriched = enrich_tree(
            tree,
            source_text,
            provider=provider,
            model=model,
            force=force,
        )
        if enriched is tree:
            skipped_count += 1
            continue

        if mode == "store":
            store.save(relpath, enriched)
            written.append(relpath)
        enriched_count += 1

    detail: dict[str, object] = {
        "mode": mode,
        "provider": provider,
        "model": model,
        "force": force,
        "targets": targets,
        "enriched": enriched_count,
        "skipped": skipped_count,
        "written": written,
    }
    return _summary_response(
        answer=f"pageindex enrich {mode}: {enriched_count} enriched, {skipped_count} skipped",
        source=["wiki"],
        confidence=1.0,
        detail=detail,
    )
