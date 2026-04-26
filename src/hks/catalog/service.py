"""Read-only source catalog service."""

from __future__ import annotations

from pathlib import Path

from hks.catalog.models import (
    CatalogSummaryDetail,
    IntegrityIssue,
    SourceCatalogEntry,
    SourceDetail,
)
from hks.catalog.validation import normalize_format, validate_pagination, validate_relpath
from hks.core.manifest import ManifestEntry, load_manifest
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError


def _assert_manifest_ready(paths: RuntimePaths) -> None:
    if not paths.manifest.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )


def _load_entries(paths: RuntimePaths) -> dict[str, ManifestEntry]:
    _assert_manifest_ready(paths)
    try:
        manifest = load_manifest(paths.manifest)
    except Exception as exc:
        raise KSError(
            "manifest.json 無法讀取",
            exit_code=ExitCode.DATAERR,
            code="MANIFEST_ERROR",
            details=[str(exc)],
        ) from exc
    return dict(manifest.entries)


def _entry_issues(paths: RuntimePaths, entry: ManifestEntry) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    raw_path = paths.raw_sources / entry.relpath
    if not raw_path.exists():
        issues.append(
            IntegrityIssue(
                severity="warning",
                code="raw_source_missing",
                message=f"raw source `{entry.relpath}` is missing",
            )
        )
    for slug in entry.derived.wiki_pages:
        if not (paths.wiki_pages / f"{slug}.md").exists():
            issues.append(
                IntegrityIssue(
                    severity="warning",
                    code="wiki_page_missing",
                    message=f"wiki page `{slug}` is missing",
                )
            )
    return issues


def _status(issues: list[IntegrityIssue]) -> str:
    if any(issue.severity == "error" for issue in issues):
        return "error"
    if issues:
        return "warning"
    return "ok"


def _entry_to_catalog(paths: RuntimePaths, entry: ManifestEntry) -> SourceCatalogEntry:
    issues = _entry_issues(paths, entry)
    return SourceCatalogEntry.from_manifest(
        entry,
        integrity_status=_status(issues),  # type: ignore[arg-type]
        issues=issues,
    )


def list_sources(
    *,
    ks_root: Path | str | None = None,
    format: str | None = None,
    relpath_query: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> CatalogSummaryDetail:
    paths = runtime_paths(ks_root)
    entries = _load_entries(paths)
    source_format = normalize_format(format)
    normalized_limit, normalized_offset = validate_pagination(limit, offset)
    catalog = [_entry_to_catalog(paths, entry) for _, entry in sorted(entries.items())]
    filtered = [
        entry
        for entry in catalog
        if (source_format is None or entry.format == source_format)
        and (not relpath_query or relpath_query in entry.relpath)
    ]
    if normalized_offset:
        filtered = filtered[normalized_offset:]
    if normalized_limit is not None:
        filtered = filtered[:normalized_limit]
    return CatalogSummaryDetail(
        operation="source.list",
        ks_root=paths.root.as_posix(),
        total_count=len(catalog),
        filtered_count=len(filtered),
        filter={
            "format": format,
            "relpath_query": relpath_query,
            "limit": limit,
            "offset": offset,
        },
        sources=filtered,
    )


def show_source(
    relpath: str,
    *,
    ks_root: Path | str | None = None,
) -> CatalogSummaryDetail:
    normalized_relpath = validate_relpath(relpath)
    paths = runtime_paths(ks_root)
    entries = _load_entries(paths)
    entry = entries.get(normalized_relpath)
    if entry is None:
        raise KSError(
            f"source `{normalized_relpath}` 不存在於 manifest",
            exit_code=ExitCode.NOINPUT,
            code="SOURCE_NOT_FOUND",
        )
    issues = _entry_issues(paths, entry)
    detail = SourceDetail.from_entry(
        entry,
        raw_source_path=(paths.raw_sources / entry.relpath).as_posix(),
        integrity_status=_status(issues),  # type: ignore[arg-type]
        issues=issues,
    )
    return CatalogSummaryDetail(
        operation="source.show",
        ks_root=paths.root.as_posix(),
        total_count=len(entries),
        filtered_count=1,
        filter={"relpath": normalized_relpath},
        source=detail,
    )


def summary_answer(detail: dict[str, object]) -> str:
    operation = detail.get("command")
    if operation == "source.list":
        filtered = detail.get("filtered_count", 0)
        total = detail.get("total_count", 0)
        return f"source catalog：{filtered} / {total} sources"
    if operation == "source.show":
        source = detail.get("source")
        if isinstance(source, dict):
            return f"source detail：{source.get('relpath')}"
    if operation == "workspace.list":
        return f"workspace catalog：{detail.get('total_count', 0)} workspaces"
    if operation == "workspace.use":
        return f"workspace selected：{detail.get('workspace_id')}"
    if isinstance(operation, str) and operation.startswith("workspace."):
        return f"workspace operation completed：{operation}"
    return "catalog operation completed"
