"""Shared ingestion data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from hks.core.manifest import SourceFormat
from hks.ingest.office_common import Segment, SkippedSegment


@dataclass(slots=True)
class ParsedDocument:
    title: str
    body: str
    format: SourceFormat
    segments: list[Segment] = field(default_factory=list)
    skipped_segments: list[SkippedSegment] = field(default_factory=list)
    parser_fingerprint: str = ""


@dataclass(slots=True)
class ExtractedDocument:
    title: str
    summary: str
    body: str
    chunks: list[str]
    chunk_metadata: list[dict[str, object]] = field(default_factory=list)


@dataclass(slots=True)
class IngestIssue:
    path: str
    reason: str
    kind: Literal["skipped", "failed"]


FileStatus = Literal["created", "updated", "skipped", "failed", "unsupported"]
PptxNotesMode = Literal["included", "excluded"]


@dataclass(slots=True)
class IngestFileReport:
    path: str
    status: FileStatus
    reason: str | None = None
    skipped_segments: list[SkippedSegment] = field(default_factory=list)
    pptx_notes: PptxNotesMode | None = None


@dataclass(slots=True)
class IngestSummary:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[IngestIssue] = field(default_factory=list)
    failures: list[IngestIssue] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    files: list[IngestFileReport] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.created) + len(self.updated)

    def answer(self) -> str:
        return (
            f"ingest 完成：created {len(self.created)}、updated {len(self.updated)}、"
            f"skipped {len(self.skipped)}、failed {len(self.failures)}"
        )
