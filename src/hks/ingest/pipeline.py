"""Ingestion orchestrator."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from hks.core.lock import file_lock
from hks.core.manifest import (
    DerivedArtifacts,
    ManifestEntry,
    SourceFormat,
    compute_sha256,
    resume_or_rebuild,
    save_manifest,
    source_format_from_path,
    utc_now_iso,
)
from hks.core.paths import runtime_paths
from hks.core.text_models import TextModelBackend
from hks.errors import ExitCode, KSError
from hks.ingest import extractor, normalizer
from hks.ingest.models import IngestIssue, IngestSummary, ParsedDocument
from hks.ingest.parsers import md as md_parser
from hks.ingest.parsers import pdf as pdf_parser
from hks.ingest.parsers import txt as txt_parser
from hks.storage.vector import VectorChunk, VectorStore
from hks.storage.wiki import EventStatus, LogEntry, WikiStore

PARSERS: dict[SourceFormat, Callable[[Path], ParsedDocument]] = {
    "txt": txt_parser.parse,
    "md": md_parser.parse,
    "pdf": pdf_parser.parse,
}


def max_file_mb() -> int:
    return int(os.environ.get("HKS_MAX_FILE_MB", "200"))


def discover_files(path: Path) -> list[Path]:
    if not path.exists():
        raise KSError(
            f"path not found: {path}",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="請提供存在的檔案或目錄",
        )
    if path.is_file():
        return [path]
    return sorted(file_path for file_path in path.rglob("*") if file_path.is_file())


def parse_file(path: Path, source_format: SourceFormat) -> ParsedDocument:
    parser = PARSERS[source_format]
    return parser(path)


def delete_artifacts(
    *,
    wiki_store: WikiStore,
    vector_store: VectorStore,
    relpath: str,
    wiki_pages: list[str],
    vector_ids: list[str],
) -> None:
    wiki_store.delete_pages(wiki_pages)
    vector_store.delete(vector_ids)
    raw_source = wiki_store.paths.raw_sources / relpath
    if raw_source.exists():
        raw_source.unlink()


def relative_path(source_root: Path, file_path: Path) -> str:
    if source_root.is_file():
        return file_path.name
    return file_path.relative_to(source_root).as_posix()


def ingest(path: Path, *, prune: bool = False) -> IngestSummary:
    source_root = path.resolve(strict=False)
    files = discover_files(source_root)
    paths = runtime_paths()
    backend = TextModelBackend()
    wiki_store = WikiStore(paths)
    vector_store = VectorStore(paths, backend=backend)
    summary = IngestSummary()

    with file_lock(paths.lock):
        manifest = resume_or_rebuild(paths)
        seen_relpaths: set[str] = set()
        for file_path in files:
            relpath = relative_path(source_root, file_path)
            seen_relpaths.add(relpath)
            source_format = source_format_from_path(file_path)
            if source_format is None:
                summary.skipped.append(
                    IngestIssue(path=relpath, reason="unsupported", kind="skipped")
                )
                wiki_store.append_log(
                    LogEntry(
                        timestamp=utc_now_iso(),
                        event="ingest",
                        status="unsupported",
                        target=f"raw_sources/{relpath}",
                        reason="unsupported",
                    )
                )
                continue

            sha256 = compute_sha256(file_path)
            existing = manifest.entries.get(relpath)
            if existing and existing.sha256 == sha256:
                summary.skipped.append(
                    IngestIssue(path=relpath, reason="hash unchanged", kind="skipped")
                )
                wiki_store.append_log(
                    LogEntry(
                        timestamp=utc_now_iso(),
                        event="ingest",
                        status="skipped",
                        target=f"raw_sources/{relpath}",
                        reason="hash unchanged",
                    )
                )
                continue

            if file_path.stat().st_size > max_file_mb() * 1024 * 1024:
                summary.failures.append(
                    IngestIssue(path=relpath, reason="oversized", kind="failed")
                )
                wiki_store.append_log(
                    LogEntry(
                        timestamp=utc_now_iso(),
                        event="ingest",
                        status="failed",
                        target=f"raw_sources/{relpath}",
                        reason="oversized",
                    )
                )
                continue

            try:
                parsed = parse_file(file_path, source_format)
                normalized_text = normalizer.normalize_text(parsed.body)
            except KSError as error:
                if error.exit_code == ExitCode.DATAERR:
                    summary.failures.append(
                        IngestIssue(path=relpath, reason=error.code.lower(), kind="failed")
                    )
                    wiki_store.append_log(
                        LogEntry(
                            timestamp=utc_now_iso(),
                            event="ingest",
                            status="failed",
                            target=f"raw_sources/{relpath}",
                            reason=error.code.lower(),
                        )
                    )
                    continue
                raise

            if not normalized_text.strip():
                if existing:
                    delete_artifacts(
                        wiki_store=wiki_store,
                        vector_store=vector_store,
                        relpath=relpath,
                        wiki_pages=existing.derived.wiki_pages,
                        vector_ids=existing.derived.vector_ids,
                    )
                    manifest.entries.pop(relpath, None)
                    save_manifest(manifest, paths.manifest)
                summary.skipped.append(IngestIssue(path=relpath, reason="empty", kind="skipped"))
                wiki_store.append_log(
                    LogEntry(
                        timestamp=utc_now_iso(),
                        event="ingest",
                        status="skipped",
                        target=f"raw_sources/{relpath}",
                        reason="empty",
                    )
                )
                continue

            if existing:
                delete_artifacts(
                    wiki_store=wiki_store,
                    vector_store=vector_store,
                    relpath=relpath,
                    wiki_pages=existing.derived.wiki_pages,
                    vector_ids=existing.derived.vector_ids,
                )

            chunks = normalizer.chunk(normalized_text, backend=backend)
            extracted = extractor.extract(
                relpath=relpath,
                sha256=sha256,
                parsed=parsed,
                normalized_text=normalized_text,
                chunks=chunks,
            )

            raw_target = paths.raw_sources / relpath
            raw_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, raw_target)

            preferred_slug = (
                existing.derived.wiki_pages[0] if existing and existing.derived.wiki_pages else None
            )
            page = wiki_store.write_page(
                title=extracted.title,
                summary=extracted.summary,
                body=extracted.body,
                source_relpath=relpath,
                origin="ingest",
                preferred_slug=preferred_slug,
            )
            vector_chunks = [
                VectorChunk(
                    id=f"{sha256[:8]}-{index}",
                    text=chunk_text,
                    metadata={
                        "source_relpath": relpath,
                        "chunk_idx": index,
                        "tokens": backend.count_tokens(chunk_text),
                        "format": source_format,
                        "sha256_source": sha256,
                    },
                )
                for index, chunk_text in enumerate(extracted.chunks)
            ]
            vector_ids = vector_store.add_chunks(vector_chunks)
            manifest.entries[relpath] = ManifestEntry(
                relpath=relpath,
                sha256=sha256,
                format=source_format,
                size_bytes=file_path.stat().st_size,
                ingested_at=utc_now_iso(),
                derived=DerivedArtifacts(
                    wiki_pages=[page.slug],
                    vector_ids=vector_ids,
                ),
            )
            save_manifest(manifest, paths.manifest)

            status: EventStatus = "updated" if existing else "created"
            if existing:
                summary.updated.append(relpath)
            else:
                summary.created.append(relpath)
            wiki_store.append_log(
                LogEntry(
                    timestamp=utc_now_iso(),
                    event="ingest",
                    status=status,
                    target=f"raw_sources/{relpath}",
                )
            )

        if prune and source_root.is_dir():
            stale_paths = [relpath for relpath in manifest.entries if relpath not in seen_relpaths]
            for relpath in stale_paths:
                stale_entry = manifest.entries.pop(relpath)
                delete_artifacts(
                    wiki_store=wiki_store,
                    vector_store=vector_store,
                    relpath=relpath,
                    wiki_pages=stale_entry.derived.wiki_pages,
                    vector_ids=stale_entry.derived.vector_ids,
                )
                summary.pruned.append(relpath)
            if stale_paths:
                save_manifest(manifest, paths.manifest)
    return summary
