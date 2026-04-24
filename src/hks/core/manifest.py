"""Manifest persistence and SHA256 idempotency helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from hks.core.paths import RuntimePaths, runtime_paths

type SourceFormat = Literal["txt", "md", "pdf"]


@dataclass(slots=True)
class DerivedArtifacts:
    wiki_pages: list[str] = field(default_factory=list)
    vector_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "wiki_pages": self.wiki_pages,
            "vector_ids": self.vector_ids,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DerivedArtifacts:
        return cls(
            wiki_pages=list(payload.get("wiki_pages", [])),
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "relpath": self.relpath,
            "sha256": self.sha256,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "ingested_at": self.ingested_at,
            "derived": self.derived.to_dict(),
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
    if suffix in {"txt", "md", "pdf"}:
        return cast(SourceFormat, suffix)
    return None


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
