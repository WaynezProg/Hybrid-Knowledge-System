"""Source scanner for watch plans."""

from __future__ import annotations

from pathlib import Path

from hks.core.manifest import (
    ManifestEntry,
    classify_supported_file_issue,
    compute_sha256,
    detect_source_format,
    source_format_from_path,
)
from hks.core.paths import RuntimePaths
from hks.ingest.fingerprint import ParserFlags, compute_parser_fingerprint
from hks.watch.models import WatchIssue, WatchSource, WatchSourceState, zero_source_counts


def scan_sources(
    *,
    paths: RuntimePaths,
    manifest_entries: dict[str, ManifestEntry],
    source_roots: list[Path],
) -> tuple[list[WatchSource], list[WatchIssue], dict[str, int]]:
    issues: list[WatchIssue] = []
    roots = source_roots or [paths.raw_sources]
    if not source_roots:
        issues.append(
            WatchIssue(
                severity="info",
                code="external_source_roots_not_configured",
                message="source_roots not provided; scanned raw_sources only",
                source_ref=paths.raw_sources.as_posix(),
            )
        )

    sources: dict[str, WatchSource] = {}
    seen: set[str] = set()
    for root in roots:
        resolved_root = root.expanduser().resolve(strict=False)
        if not resolved_root.exists():
            issues.append(
                WatchIssue(
                    severity="warning",
                    code="source_root_missing",
                    message=f"source root `{resolved_root}` does not exist",
                    source_ref=resolved_root.as_posix(),
                )
            )
            continue
        files = [resolved_root] if resolved_root.is_file() else sorted(resolved_root.rglob("*"))
        for file_path in files:
            if not file_path.is_file():
                continue
            relpath = _relative_path(resolved_root, file_path)
            seen.add(relpath)
            source = _classify_file(
                file_path,
                relpath=relpath,
                root=resolved_root,
                existing=manifest_entries.get(relpath),
            )
            sources[relpath] = source

    for relpath, entry in sorted(manifest_entries.items()):
        if relpath not in seen:
            sources.setdefault(
                relpath,
                WatchSource(
                    relpath=relpath,
                    state="missing",
                    format=entry.format,
                    manifest_sha256=entry.sha256,
                    manifest_parser_fingerprint=entry.parser_fingerprint,
                    issues=[
                        WatchIssue(
                            severity="warning",
                            code="source_missing",
                            message=f"manifest source `{relpath}` was not found in watch roots",
                            source_ref=relpath,
                        )
                    ],
                ),
            )

    counts = zero_source_counts()
    for source in sources.values():
        counts[source.state] += 1
    return sorted(sources.values(), key=lambda item: item.relpath), issues, counts


def _relative_path(root: Path, file_path: Path) -> str:
    if root.is_file():
        return file_path.name
    return file_path.relative_to(root).as_posix()


def _classify_file(
    file_path: Path,
    *,
    relpath: str,
    root: Path,
    existing: ManifestEntry | None,
) -> WatchSource:
    suffix_format = source_format_from_path(file_path)
    source_format = detect_source_format(file_path)
    if source_format is None and suffix_format in {"txt", "md"}:
        source_format = suffix_format
    if source_format is None:
        issue = (
            classify_supported_file_issue(file_path)
            if suffix_format is not None
            else "unsupported"
        ) or "unsupported"
        state: WatchSourceState = "corrupt" if issue == "corrupt" else "unsupported"
        return WatchSource(
            relpath=relpath,
            state=state,
            format=suffix_format,
            size_bytes=file_path.stat().st_size,
            root_path=root.as_posix(),
            path=file_path.as_posix(),
            issues=[
                WatchIssue(
                    severity="warning",
                    code=issue,
                    message=f"source `{relpath}` is {issue}",
                    source_ref=relpath,
                )
            ],
        )

    sha256 = compute_sha256(file_path)
    parser_fingerprint = compute_parser_fingerprint(source_format, ParserFlags())
    if existing is None:
        source_state: WatchSourceState = "new"
    elif existing.sha256 != sha256 or existing.parser_fingerprint != parser_fingerprint:
        source_state = "stale"
    else:
        source_state = "unchanged"
    return WatchSource(
        relpath=relpath,
        state=source_state,
        format=source_format,
        current_sha256=sha256,
        manifest_sha256=existing.sha256 if existing else None,
        current_parser_fingerprint=parser_fingerprint,
        manifest_parser_fingerprint=existing.parser_fingerprint if existing else None,
        size_bytes=file_path.stat().st_size,
        root_path=root.as_posix(),
        path=file_path.as_posix(),
    )
