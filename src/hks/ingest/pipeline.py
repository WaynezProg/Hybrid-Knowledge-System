"""Ingestion orchestrator."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hks.core.config import config_value
from hks.core.lock import file_lock
from hks.core.manifest import (
    DerivedArtifacts,
    ManifestEntry,
    SourceFormat,
    classify_supported_file_issue,
    compute_sha256,
    detect_source_format,
    resume_or_rebuild,
    save_manifest,
    source_format_from_path,
    utc_now_iso,
)
from hks.core.paths import runtime_paths
from hks.core.text_models import TextModelBackend
from hks.errors import ExitCode, KSError
from hks.graph.extract import extract_document_graph
from hks.graph.store import GraphStore
from hks.ingest import extractor, normalizer
from hks.ingest.fingerprint import (
    ParserFlags,
    are_fingerprints_compatible,
    compute_parser_fingerprint,
)
from hks.ingest.guards import (
    OversizeError,
    load_image_limits,
    load_office_limits,
    preflight_size_check,
    with_timeout,
)
from hks.ingest.models import (
    FileStatus,
    IngestFileReport,
    IngestIssue,
    IngestSummary,
    ParsedDocument,
    PptxNotesMode,
)
from hks.ingest.office_common import SkippedSegment
from hks.ingest.parsers import docx as docx_parser
from hks.ingest.parsers import image as image_parser
from hks.ingest.parsers import md as md_parser
from hks.ingest.parsers import pdf as pdf_parser
from hks.ingest.parsers import pptx as pptx_parser
from hks.ingest.parsers import txt as txt_parser
from hks.ingest.parsers import xlsx as xlsx_parser
from hks.storage.vector import VectorChunk, VectorStore
from hks.storage.wiki import EventStatus, LogEntry, WikiStore

# Office parsers are flag-aware; other formats ignore ParserFlags.
OfficeParser = Callable[[Path, ParserFlags], ParsedDocument]
ImageParser = Callable[[Path, SourceFormat], ParsedDocument]
LegacyParser = Callable[[Path], ParsedDocument]

_LEGACY_PARSERS: dict[SourceFormat, LegacyParser] = {
    "txt": txt_parser.parse,
    "md": md_parser.parse,
    "pdf": pdf_parser.parse,
}

_OFFICE_PARSERS: dict[SourceFormat, OfficeParser] = {
    "docx": docx_parser.parse,
    "xlsx": xlsx_parser.parse,
    "pptx": pptx_parser.parse,
}

_IMAGE_PARSERS: dict[SourceFormat, ImageParser] = {
    "png": image_parser.parse,
    "jpg": image_parser.parse,
    "jpeg": image_parser.parse,
}

PARSERS: dict[SourceFormat, Callable[..., ParsedDocument]] = {
    **_LEGACY_PARSERS,
    **_OFFICE_PARSERS,
    **_IMAGE_PARSERS,
}


def max_file_mb() -> int:
    return int(config_value("HKS_MAX_FILE_MB") or "200")


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


def parse_file(path: Path, source_format: SourceFormat, flags: ParserFlags) -> ParsedDocument:
    if source_format in _OFFICE_PARSERS:
        return _OFFICE_PARSERS[source_format](path, flags)
    if source_format in _IMAGE_PARSERS:
        return _IMAGE_PARSERS[source_format](path, source_format)
    return _LEGACY_PARSERS[source_format](path)


def delete_artifacts(
    *,
    wiki_store: WikiStore,
    graph_store: GraphStore | None,
    vector_store: VectorStore,
    relpath: str,
    wiki_pages: list[str],
    vector_ids: list[str],
) -> None:
    wiki_store.delete_pages(wiki_pages)
    if graph_store is not None:
        graph_store.delete_document(relpath)
    vector_store.delete(vector_ids)
    raw_source = wiki_store.paths.raw_sources / relpath
    if raw_source.exists():
        raw_source.unlink()


def relative_path(source_root: Path, file_path: Path) -> str:
    if source_root.is_file():
        return file_path.name
    return file_path.relative_to(source_root).as_posix()


def _vector_chunk_id(sha256: str, parser_fingerprint: str, index: int) -> str:
    digest = hashlib.sha1(parser_fingerprint.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{sha256[:8]}-{digest}-{index}"


def _log_and_issue(
    *,
    wiki_store: WikiStore,
    relpath: str,
    status: EventStatus,
    reason: str | None,
    skipped_segments: list[SkippedSegment] | None = None,
    pptx_notes: PptxNotesMode | None = None,
) -> None:
    wiki_store.append_log(
        LogEntry(
            timestamp=utc_now_iso(),
            event="ingest",
            status=status,
            target=f"raw_sources/{relpath}",
            reason=reason,
            skipped_segments=list(skipped_segments or []),
            pptx_notes=pptx_notes,
        )
    )


def ingest(path: Path, *, prune: bool = False, pptx_notes: bool = True) -> IngestSummary:
    source_root = path.resolve(strict=False)
    files = discover_files(source_root)
    paths = runtime_paths()
    backend = TextModelBackend()
    wiki_store = WikiStore(paths)
    graph_store = GraphStore(paths)
    vector_store = VectorStore(paths, backend=backend)
    summary = IngestSummary()
    limits = load_office_limits()
    image_limits = load_image_limits()
    flags = ParserFlags(pptx_notes=pptx_notes)

    with file_lock(paths.lock):
        manifest = resume_or_rebuild(paths)
        seen_relpaths: set[str] = set()
        for file_path in files:
            relpath = relative_path(source_root, file_path)
            seen_relpaths.add(relpath)
            suffix_format = source_format_from_path(file_path)
            if file_path.stat().st_size == 0 and suffix_format is not None:
                reason = "empty_file"
                summary.skipped.append(IngestIssue(path=relpath, reason=reason, kind="skipped"))
                summary.files.append(
                    IngestFileReport(
                        path=relpath,
                        status="skipped",
                        reason=reason,
                        source_format=suffix_format,
                    )
                )
                _log_and_issue(
                    wiki_store=wiki_store, relpath=relpath, status="skipped", reason=reason
                )
                continue
            source_format = detect_source_format(file_path)
            # Fall through to suffix-only detection for txt/md whose sniff is skipped.
            if source_format is None and suffix_format in {"txt", "md"}:
                source_format = suffix_format

            if source_format is None:
                reason = (
                    classify_supported_file_issue(file_path)
                    if suffix_format is not None
                    else "unsupported"
                ) or "unsupported"
                status: FileStatus = "failed" if suffix_format is not None else "unsupported"
                if status == "unsupported":
                    summary.skipped.append(IngestIssue(path=relpath, reason=reason, kind="skipped"))
                else:
                    summary.failures.append(IngestIssue(path=relpath, reason=reason, kind="failed"))
                summary.files.append(
                    IngestFileReport(
                        path=relpath,
                        status=status,
                        reason=reason,
                        source_format=suffix_format,
                    )
                )
                _log_and_issue(wiki_store=wiki_store, relpath=relpath, status=status, reason=reason)
                continue

            is_office = source_format in _OFFICE_PARSERS
            is_image = source_format in _IMAGE_PARSERS

            # Oversize preflight: Office uses its own limit, others use legacy HKS_MAX_FILE_MB.
            try:
                if is_office:
                    preflight_size_check(file_path, limits.max_file_mb)
                elif is_image:
                    preflight_size_check(file_path, image_limits.max_file_mb)
                else:
                    preflight_size_check(file_path, max_file_mb())
            except OversizeError:
                reason = "oversized"
                summary.failures.append(IngestIssue(path=relpath, reason=reason, kind="failed"))
                summary.files.append(
                    IngestFileReport(
                        path=relpath,
                        status="failed",
                        reason=reason,
                        source_format=source_format,
                    )
                )
                _log_and_issue(
                    wiki_store=wiki_store, relpath=relpath, status="failed", reason=reason
                )
                continue

            sha256 = compute_sha256(file_path)
            current_fp = compute_parser_fingerprint(source_format, flags)
            existing = manifest.entries.get(relpath)
            if (
                existing
                and existing.sha256 == sha256
                and are_fingerprints_compatible(existing.parser_fingerprint, current_fp)
            ):
                reason = "hash unchanged"
                summary.skipped.append(IngestIssue(path=relpath, reason=reason, kind="skipped"))
                summary.files.append(
                    IngestFileReport(path=relpath, status="skipped", reason="hash_unchanged")
                )
                _log_and_issue(
                    wiki_store=wiki_store, relpath=relpath, status="skipped", reason=reason
                )
                continue

            # Parse with per-file timeout (Office only; legacy parsers run unbounded).
            try:
                if is_office:
                    with with_timeout(limits.timeout_seconds):
                        parsed = parse_file(file_path, source_format, flags)
                elif is_image:
                    with with_timeout(image_limits.timeout_seconds):
                        parsed = parse_file(file_path, source_format, flags)
                else:
                    parsed = parse_file(file_path, source_format, flags)
            except TimeoutError:
                reason = "timeout"
                summary.failures.append(IngestIssue(path=relpath, reason=reason, kind="failed"))
                summary.files.append(
                    IngestFileReport(
                        path=relpath,
                        status="failed",
                        reason=reason,
                        source_format=source_format,
                    )
                )
                _log_and_issue(
                    wiki_store=wiki_store, relpath=relpath, status="failed", reason=reason
                )
                continue
            except KSError as error:
                if error.exit_code == ExitCode.DATAERR:
                    reason = error.code.lower()
                    summary.failures.append(IngestIssue(path=relpath, reason=reason, kind="failed"))
                    summary.files.append(
                        IngestFileReport(
                            path=relpath,
                            status="failed",
                            reason=reason,
                            source_format=source_format,
                        )
                    )
                    _log_and_issue(
                        wiki_store=wiki_store, relpath=relpath, status="failed", reason=reason
                    )
                    continue
                raise

            # Segment-aware path when parser produced rich segments.
            if parsed.segments:
                body_text = normalizer.segments_to_body(parsed.segments)
                normalized_text = normalizer.normalize_text(body_text)
                seg_chunks = normalizer.segment_aware_chunks(parsed.segments, backend=backend)
                chunks = [text for text, _ in seg_chunks]
                chunk_metadata: list[dict[str, Any]] = [meta for _, meta in seg_chunks]
            else:
                normalized_text = normalizer.normalize_text(parsed.body)
                chunks = normalizer.chunk(normalized_text, backend=backend)
                chunk_metadata = [{} for _ in chunks]

            if not normalized_text.strip():
                if existing:
                    delete_artifacts(
                        wiki_store=wiki_store,
                        graph_store=graph_store,
                        vector_store=vector_store,
                        relpath=relpath,
                        wiki_pages=existing.derived.wiki_pages,
                        vector_ids=existing.derived.vector_ids,
                    )
                    manifest.entries.pop(relpath, None)
                    save_manifest(manifest, paths.manifest)
                reason = _empty_skip_reason(parsed)
                summary.skipped.append(IngestIssue(path=relpath, reason=reason, kind="skipped"))
                summary.files.append(
                    IngestFileReport(
                        path=relpath,
                        status="skipped",
                        reason=reason,
                        source_format=source_format,
                        skipped_segments=list(parsed.skipped_segments),
                        ocr_chunks=0 if is_image else None,
                        ocr_engine=_image_engine(parsed) if is_image else None,
                    )
                )
                _log_and_issue(
                    wiki_store=wiki_store,
                    relpath=relpath,
                    status="skipped",
                    reason=reason,
                    skipped_segments=parsed.skipped_segments,
                )
                continue

            if existing:
                delete_artifacts(
                    wiki_store=wiki_store,
                    graph_store=graph_store,
                    vector_store=vector_store,
                    relpath=relpath,
                    wiki_pages=existing.derived.wiki_pages,
                    vector_ids=existing.derived.vector_ids,
                )

            extracted = extractor.extract(
                relpath=relpath,
                sha256=sha256,
                parsed=parsed,
                normalized_text=normalized_text,
                chunks=chunks,
                chunk_metadata=chunk_metadata,
            )

            raw_target = paths.raw_sources / relpath
            raw_target.parent.mkdir(parents=True, exist_ok=True)
            preferred_slug = (
                existing.derived.wiki_pages[0] if existing and existing.derived.wiki_pages else None
            )
            raw_backup = raw_target.read_bytes() if raw_target.exists() else None
            page_backup_path = (
                wiki_store.paths.wiki_pages / f"{preferred_slug}.md"
                if preferred_slug is not None
                else None
            )
            page_backup = (
                page_backup_path.read_text(encoding="utf-8")
                if page_backup_path is not None and page_backup_path.exists()
                else None
            )
            graph_backup = (
                graph_store.graph_path.read_text(encoding="utf-8")
                if graph_store.graph_path.exists()
                else None
            )

            vector_chunks = [
                VectorChunk(
                    id=_vector_chunk_id(sha256, current_fp, index),
                    text=chunk_text,
                    metadata={
                        "source_relpath": relpath,
                        "chunk_idx": index,
                        "tokens": backend.count_tokens(chunk_text),
                        "format": source_format,
                        "source_format": source_format,
                        "sha256_source": sha256,
                        **_flatten_chunk_metadata(
                            extracted.chunk_metadata[index]
                            if index < len(extracted.chunk_metadata)
                            else {}
                        ),
                    },
                )
                for index, chunk_text in enumerate(extracted.chunks)
            ]
            page_slug: str | None = None
            vector_ids: list[str] = []
            graph_node_ids: list[str] = []
            graph_edge_ids: list[str] = []
            try:
                shutil.copy2(file_path, raw_target)
                page = wiki_store.write_page(
                    title=extracted.title,
                    summary=extracted.summary,
                    body=extracted.body,
                    source_relpath=relpath,
                    origin="ingest",
                    preferred_slug=preferred_slug,
                )
                page_slug = page.slug
                graph_artifacts = extract_document_graph(
                    relpath=relpath,
                    title=extracted.title,
                    body=normalized_text,
                    wiki_slug=page.slug,
                )
                graph_store.replace_document(relpath, graph_artifacts)
                graph_node_ids = [node.id for node in graph_artifacts.nodes]
                graph_edge_ids = [edge.id for edge in graph_artifacts.edges]
                vector_ids = vector_store.add_chunks(vector_chunks)
                manifest.entries[relpath] = ManifestEntry(
                    relpath=relpath,
                    sha256=sha256,
                    format=source_format,
                    size_bytes=file_path.stat().st_size,
                    ingested_at=utc_now_iso(),
                    derived=DerivedArtifacts(
                        wiki_pages=[page.slug],
                        graph_nodes=graph_node_ids,
                        graph_edges=graph_edge_ids,
                        vector_ids=vector_ids,
                    ),
                    parser_fingerprint=current_fp,
                )
                save_manifest(manifest, paths.manifest)
            except Exception:
                if vector_ids:
                    vector_store.delete(vector_ids)
                if existing is not None:
                    manifest.entries[relpath] = existing
                else:
                    manifest.entries.pop(relpath, None)
                if page_slug is not None:
                    if page_backup_path is not None and page_backup is not None:
                        page_backup_path.write_text(page_backup, encoding="utf-8")
                        wiki_store.rebuild_index()
                    else:
                        wiki_store.delete_pages([page_slug])
                if raw_backup is not None:
                    raw_target.parent.mkdir(parents=True, exist_ok=True)
                    raw_target.write_bytes(raw_backup)
                elif raw_target.exists():
                    raw_target.unlink()
                if graph_backup is not None:
                    graph_store.graph_path.parent.mkdir(parents=True, exist_ok=True)
                    graph_store.graph_path.write_text(graph_backup, encoding="utf-8")
                elif graph_store.graph_path.exists():
                    graph_store.graph_path.unlink()
                raise

            if existing and existing.derived.vector_ids:
                stale_vector_ids = sorted(set(existing.derived.vector_ids) - set(vector_ids))
                vector_store.delete(stale_vector_ids)

            result_status: FileStatus = "updated" if existing else "created"
            if existing:
                summary.updated.append(relpath)
            else:
                summary.created.append(relpath)
            notes_mode: PptxNotesMode | None
            if source_format == "pptx":
                notes_mode = "included" if flags.pptx_notes else "excluded"
            else:
                notes_mode = None
            summary.files.append(
                IngestFileReport(
                    path=relpath,
                    status=result_status,
                    source_format=source_format,
                    skipped_segments=list(parsed.skipped_segments),
                    pptx_notes=notes_mode,
                    ocr_chunks=len(parsed.segments) if is_image else None,
                    ocr_confidence_min=_image_confidence(parsed, min) if is_image else None,
                    ocr_confidence_max=_image_confidence(parsed, max) if is_image else None,
                    ocr_engine=_image_engine(parsed) if is_image else None,
                )
            )
            _log_and_issue(
                wiki_store=wiki_store,
                relpath=relpath,
                status=result_status,
                reason=None,
                skipped_segments=parsed.skipped_segments,
                pptx_notes=notes_mode,
            )

        if prune and source_root.is_dir():
            stale_paths = [relpath for relpath in manifest.entries if relpath not in seen_relpaths]
            for relpath in stale_paths:
                stale_entry = manifest.entries.pop(relpath)
                delete_artifacts(
                    wiki_store=wiki_store,
                    graph_store=graph_store,
                    vector_store=vector_store,
                    relpath=relpath,
                    wiki_pages=stale_entry.derived.wiki_pages,
                    vector_ids=stale_entry.derived.vector_ids,
                )
                summary.pruned.append(relpath)
            if stale_paths:
                save_manifest(manifest, paths.manifest)
    return summary


def _flatten_chunk_metadata(
    metadata: dict[str, object],
) -> dict[str, str | int | float | bool]:
    """Chroma metadata values must be primitive; coerce and drop None."""

    flattened: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, str | int | float | bool):
            flattened[key] = value
        elif value is not None:
            flattened[key] = str(value)
    return flattened


def _empty_skip_reason(parsed: ParsedDocument) -> str:
    if any(segment.type == "ocr_empty" for segment in parsed.skipped_segments):
        return "ocr_empty"
    return "empty"


def _image_confidence(
    parsed: ParsedDocument,
    reducer: Callable[[list[float]], float],
) -> float | None:
    values = [
        float(segment.metadata["ocr_confidence"])
        for segment in parsed.segments
        if "ocr_confidence" in segment.metadata
    ]
    if not values:
        return None
    return round(reducer(values), 4)


def _image_engine(parsed: ParsedDocument) -> str | None:
    for segment in parsed.segments:
        source_engine = segment.metadata.get("source_engine")
        if isinstance(source_engine, str) and source_engine:
            return source_engine
    return None
