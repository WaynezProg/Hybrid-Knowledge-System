"""Models for manifest-derived source catalog responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from hks.core.manifest import ManifestEntry, SourceFormat

type IntegrityStatus = Literal["ok", "warning", "error", "unknown"]
type CatalogOperation = Literal[
    "source.list",
    "source.show",
    "workspace.list",
    "workspace.show",
    "workspace.register",
    "workspace.remove",
    "workspace.use",
]


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class DerivedCounts:
    wiki_pages: int
    graph_nodes: int
    graph_edges: int
    vector_ids: int

    @classmethod
    def from_entry(cls, entry: ManifestEntry) -> DerivedCounts:
        return cls(
            wiki_pages=len(entry.derived.wiki_pages),
            graph_nodes=len(entry.derived.graph_nodes),
            graph_edges=len(entry.derived.graph_edges),
            vector_ids=len(entry.derived.vector_ids),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "wiki_pages": self.wiki_pages,
            "graph_nodes": self.graph_nodes,
            "graph_edges": self.graph_edges,
            "vector_ids": self.vector_ids,
        }


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    relpath: str
    format: SourceFormat
    size_bytes: int
    ingested_at: str
    sha256: str
    sha256_prefix: str
    parser_fingerprint: str
    derived_counts: DerivedCounts
    integrity_status: IntegrityStatus
    issues: list[IntegrityIssue] = field(default_factory=list)
    query_hint: str = "Use `ks query \"...\" --writeback=no` after selecting this KS_ROOT."

    @classmethod
    def from_manifest(
        cls,
        entry: ManifestEntry,
        *,
        integrity_status: IntegrityStatus = "unknown",
        issues: list[IntegrityIssue] | None = None,
    ) -> SourceCatalogEntry:
        return cls(
            relpath=entry.relpath,
            format=entry.format,
            size_bytes=entry.size_bytes,
            ingested_at=entry.ingested_at,
            sha256=entry.sha256,
            sha256_prefix=entry.sha256[:12],
            parser_fingerprint=entry.parser_fingerprint,
            derived_counts=DerivedCounts.from_entry(entry),
            integrity_status=integrity_status,
            issues=list(issues or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "relpath": self.relpath,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "ingested_at": self.ingested_at,
            "sha256": self.sha256,
            "sha256_prefix": self.sha256_prefix,
            "parser_fingerprint": self.parser_fingerprint,
            "derived_counts": self.derived_counts.to_dict(),
            "integrity_status": self.integrity_status,
            "issues": [issue.to_dict() for issue in self.issues],
            "query_hint": self.query_hint,
        }


@dataclass(frozen=True, slots=True)
class SourceDetail(SourceCatalogEntry):
    raw_source_path: str = ""
    derived: dict[str, list[str]] = field(default_factory=dict)
    integrity_checks: list[IntegrityIssue] = field(default_factory=list)

    @classmethod
    def from_entry(
        cls,
        entry: ManifestEntry,
        *,
        raw_source_path: str,
        integrity_status: IntegrityStatus,
        issues: list[IntegrityIssue],
    ) -> SourceDetail:
        return cls(
            relpath=entry.relpath,
            format=entry.format,
            size_bytes=entry.size_bytes,
            ingested_at=entry.ingested_at,
            sha256=entry.sha256,
            sha256_prefix=entry.sha256[:12],
            parser_fingerprint=entry.parser_fingerprint,
            derived_counts=DerivedCounts.from_entry(entry),
            integrity_status=integrity_status,
            issues=list(issues),
            raw_source_path=raw_source_path,
            derived={
                "wiki_pages": list(entry.derived.wiki_pages),
                "graph_nodes": list(entry.derived.graph_nodes),
                "graph_edges": list(entry.derived.graph_edges),
                "vector_ids": list(entry.derived.vector_ids),
            },
            integrity_checks=list(issues),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = SourceCatalogEntry.to_dict(self)
        payload.update(
            {
                "raw_source_path": self.raw_source_path,
                "derived": self.derived,
                "integrity_checks": [issue.to_dict() for issue in self.integrity_checks],
            }
        )
        return payload


@dataclass(frozen=True, slots=True)
class CatalogSummaryDetail:
    operation: CatalogOperation
    warnings: list[str] = field(default_factory=list)
    workspace_id: str | None = None
    ks_root: str | None = None
    registry_path: str | None = None
    previous_root: str | None = None
    total_count: int | None = None
    filtered_count: int | None = None
    filter: dict[str, str | int | float | bool | None] | None = None
    sources: list[SourceCatalogEntry] | None = None
    source: SourceDetail | None = None
    workspaces: list[dict[str, Any]] | None = None
    export_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "catalog_summary",
            "command": self.operation,
            "total_count": self.total_count or 0,
            "filtered_count": self.filtered_count or 0,
            "filter": self.filter,
            "workspace_id": self.workspace_id,
            "ks_root": self.ks_root,
            "registry_path": self.registry_path,
            "previous_root": self.previous_root,
            "sources": (
                [entry.to_dict() for entry in self.sources]
                if self.sources is not None
                else None
            ),
            "source": self.source.to_dict() if self.source is not None else None,
            "workspaces": self.workspaces,
            "export_command": self.export_command,
            "warnings": self.warnings,
        }
