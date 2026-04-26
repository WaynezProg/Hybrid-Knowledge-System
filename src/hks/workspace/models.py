"""Models for named HKS workspace registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

type WorkspaceState = Literal["ready", "missing", "uninitialized", "corrupt", "duplicate_root"]


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    id: str
    label: str
    ks_root: str
    created_at: str
    updated_at: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "ks_root": self.ks_root,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkspaceRecord:
        return cls(
            id=str(payload["id"]),
            label=str(payload["label"]),
            ks_root=str(payload["ks_root"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            tags=[str(tag) for tag in payload.get("tags", [])],
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class WorkspaceRegistry:
    schema_version: int
    updated_at: str
    workspaces: dict[str, WorkspaceRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "workspaces": {
                workspace_id: record.to_dict()
                for workspace_id, record in sorted(self.workspaces.items())
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkspaceRegistry:
        records = payload.get("workspaces", {})
        if not isinstance(records, dict):
            raise ValueError("workspaces must be an object")
        return cls(
            schema_version=int(payload.get("schema_version", 1)),
            updated_at=str(payload["updated_at"]),
            workspaces={
                str(workspace_id): WorkspaceRecord.from_dict(record)
                for workspace_id, record in records.items()
                if isinstance(record, dict)
            },
        )


@dataclass(frozen=True, slots=True)
class WorkspaceStatus:
    id: str
    label: str
    ks_root: str
    status: WorkspaceState
    source_count: int
    formats: dict[str, int]
    last_ingested_at: str | None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "ks_root": self.ks_root,
            "status": self.status,
            "source_count": self.source_count,
            "formats": self.formats,
            "last_ingested_at": self.last_ingested_at,
            "issues": self.issues,
        }

