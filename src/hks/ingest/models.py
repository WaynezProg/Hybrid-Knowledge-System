"""Shared ingestion data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from hks.core.manifest import SourceFormat


@dataclass(slots=True)
class ParsedDocument:
    title: str
    body: str
    format: SourceFormat


@dataclass(slots=True)
class ExtractedDocument:
    title: str
    summary: str
    body: str
    chunks: list[str]


@dataclass(slots=True)
class IngestIssue:
    path: str
    reason: str
    kind: Literal["skipped", "failed"]


@dataclass(slots=True)
class IngestSummary:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[IngestIssue] = field(default_factory=list)
    failures: list[IngestIssue] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.created) + len(self.updated)

    def answer(self) -> str:
        return (
            f"ingest 完成：created {len(self.created)}、updated {len(self.updated)}、"
            f"skipped {len(self.skipped)}、failed {len(self.failures)}"
        )
