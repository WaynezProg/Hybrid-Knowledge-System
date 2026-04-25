"""Manifest persistence and idempotency helpers."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from hks.core.paths import RuntimePaths, runtime_paths

type SourceFormat = Literal["txt", "md", "pdf", "docx", "xlsx", "pptx", "png", "jpg", "jpeg"]

OFFICE_FORMATS: frozenset[SourceFormat] = frozenset({"docx", "xlsx", "pptx"})
IMAGE_FORMATS: frozenset[SourceFormat] = frozenset({"png", "jpg", "jpeg"})
SUPPORTED_SUFFIXES: frozenset[str] = frozenset(
    {"txt", "md", "pdf", "docx", "xlsx", "pptx", "png", "jpg", "jpeg"}
)

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_OOXML_MAIN_PART: dict[Literal["docx", "xlsx", "pptx"], str] = {
    "docx": "word/document.xml",
    "xlsx": "xl/workbook.xml",
    "pptx": "ppt/presentation.xml",
}


@dataclass(slots=True)
class DerivedArtifacts:
    wiki_pages: list[str] = field(default_factory=list)
    graph_nodes: list[str] = field(default_factory=list)
    graph_edges: list[str] = field(default_factory=list)
    vector_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "wiki_pages": self.wiki_pages,
            "graph_nodes": self.graph_nodes,
            "graph_edges": self.graph_edges,
            "vector_ids": self.vector_ids,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DerivedArtifacts:
        return cls(
            wiki_pages=list(payload.get("wiki_pages", [])),
            graph_nodes=list(payload.get("graph_nodes", [])),
            graph_edges=list(payload.get("graph_edges", [])),
            vector_ids=list(payload.get("vector_ids", [])),
        )


@dataclass(slots=True)
class ManifestEntry:
    relpath: str
    sha256: str
    format: SourceFormat
    size_bytes: int
    ingested_at: str
    derived: DerivedArtifacts = field(default_factory=DerivedArtifacts)
    parser_fingerprint: str = "*"

    def to_dict(self) -> dict[str, Any]:
        return {
            "relpath": self.relpath,
            "sha256": self.sha256,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "ingested_at": self.ingested_at,
            "derived": self.derived.to_dict(),
            "parser_fingerprint": self.parser_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ManifestEntry:
        return cls(
            relpath=str(payload["relpath"]),
            sha256=str(payload["sha256"]),
            format=cast(SourceFormat, payload["format"]),
            size_bytes=int(payload["size_bytes"]),
            ingested_at=str(payload["ingested_at"]),
            derived=DerivedArtifacts.from_dict(cast(dict[str, Any], payload.get("derived", {}))),
            parser_fingerprint=str(payload.get("parser_fingerprint", "*")),
        )


@dataclass(slots=True)
class Manifest:
    version: int = 1
    entries: dict[str, ManifestEntry] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "entries": {
                relpath: entry.to_dict()
                for relpath, entry in sorted(self.entries.items(), key=lambda item: item[0])
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Manifest:
        entries_payload = cast(dict[str, dict[str, Any]], payload.get("entries", {}))
        return cls(
            version=int(payload.get("version", 1)),
            entries={
                relpath: ManifestEntry.from_dict(entry)
                for relpath, entry in entries_payload.items()
            },
        )


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def source_format_from_path(path: Path) -> SourceFormat | None:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in SUPPORTED_SUFFIXES:
        return cast(SourceFormat, suffix)
    return None


def _read_head(path: Path, n: int) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(n)
    except OSError:
        return b""


def detect_source_format(path: Path) -> SourceFormat | None:
    """Return the dispatch format, using suffix + lightweight content sniffing.

    - Suffix is the primary signal (FR-002).
    - PDF / OOXML suffixes additionally verify magic bytes so that a truncated
      or mislabeled file lands in `corrupt` during ingest instead of crashing
      inside the wrong parser.
    - txt / md skip sniffing to preserve Phase 1 cost profile.
    """

    suffix_format = source_format_from_path(path)
    if suffix_format is None:
        return None
    if suffix_format == "pdf":
        head = _read_head(path, len(_PDF_MAGIC))
        if not head.startswith(_PDF_MAGIC):
            return None
        return suffix_format
    if suffix_format == "png":
        head = _read_head(path, len(_PNG_MAGIC))
        if not head.startswith(_PNG_MAGIC):
            return None
        return suffix_format
    if suffix_format in {"jpg", "jpeg"}:
        head = _read_head(path, len(_JPEG_MAGIC))
        if not head.startswith(_JPEG_MAGIC):
            return None
        return suffix_format
    if suffix_format in OFFICE_FORMATS:
        office_format = cast(Literal["docx", "xlsx", "pptx"], suffix_format)
        head = _read_head(path, max(len(_ZIP_MAGIC), len(_OLE_MAGIC)))
        if head.startswith(_OLE_MAGIC):
            return None
        if not head.startswith(_ZIP_MAGIC):
            return None
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return None
        required_parts = {
            "[Content_Types].xml",
            _OOXML_MAIN_PART[office_format],
        }
        if not required_parts.issubset(names):
            return None
        return office_format
    return suffix_format


def classify_supported_file_issue(path: Path) -> str | None:
    """Classify a supported-suffix file that failed format detection.

    Returns:
    - `encrypted` for Office files that look like OLE-encrypted containers.
    - `corrupt` for supported-suffix files that fail signature / container checks.
    - `None` for unknown suffixes.
    """

    suffix_format = source_format_from_path(path)
    if suffix_format is None:
        return None
    if suffix_format in OFFICE_FORMATS:
        head = _read_head(path, max(len(_ZIP_MAGIC), len(_OLE_MAGIC)))
        if head.startswith(_OLE_MAGIC):
            return "encrypted"
    return "corrupt"


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def load_manifest(path: Path | None = None) -> Manifest:
    manifest_path = path or runtime_paths().manifest
    if not manifest_path.exists():
        return Manifest()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return Manifest.from_dict(cast(dict[str, Any], payload))


def save_manifest(manifest: Manifest, path: Path | None = None) -> None:
    manifest_path = path or runtime_paths().manifest
    atomic_write(manifest_path, json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))


def resume_or_rebuild(paths: RuntimePaths | None = None) -> Manifest:
    resolved_paths = paths or runtime_paths()
    if resolved_paths.manifest.exists():
        return load_manifest(resolved_paths.manifest)

    rebuilt = Manifest()
    if resolved_paths.raw_sources.exists():
        for file_path in sorted(resolved_paths.raw_sources.rglob("*")):
            if not file_path.is_file():
                continue
            source_format = source_format_from_path(file_path)
            if source_format is None:
                continue
            relpath = file_path.relative_to(resolved_paths.raw_sources).as_posix()
            rebuilt.entries[relpath] = ManifestEntry(
                relpath=relpath,
                sha256=compute_sha256(file_path),
                format=source_format,
                size_bytes=file_path.stat().st_size,
                ingested_at=utc_now_iso(),
            )
        save_manifest(rebuilt, resolved_paths.manifest)
    return rebuilt
