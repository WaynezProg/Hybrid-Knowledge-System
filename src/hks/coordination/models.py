"""Coordination ledger models and validation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict, cast

from hks.errors import ExitCode, KSError

type SessionStatus = Literal["active", "stale", "closed"]
type LeaseStatus = Literal["active", "released", "expired"]
type ReferenceType = Literal[
    "wiki_page",
    "raw_source",
    "graph_node",
    "graph_edge",
    "vector_chunk",
    "lease",
    "handoff",
    "external",
]
type Severity = Literal["error", "warning", "info"]

AGENT_ID_RE = re.compile(r"^[A-Za-z0-9._@-]+$")


class ResourceReference(TypedDict):
    type: ReferenceType
    value: str
    label: NotRequired[str | None]


class CoordinationFinding(TypedDict):
    category: str
    severity: Severity
    target: str
    message: str


class CoordinationConflict(TypedDict):
    code: Literal["LEASE_CONFLICT"]
    resource_key: str
    active_lease_id: str
    owner_agent_id: str


class CoordinationEvent(TypedDict):
    event_id: str
    event_type: str
    created_at: str
    payload: dict[str, Any]


@dataclass(slots=True)
class AgentSession:
    session_id: str
    agent_id: str
    started_at: str
    last_seen_at: str
    status: SessionStatus = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "started_at": self.started_at,
            "last_seen_at": self.last_seen_at,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentSession:
        return cls(
            session_id=str(payload["session_id"]),
            agent_id=str(payload["agent_id"]),
            started_at=str(payload["started_at"]),
            last_seen_at=str(payload["last_seen_at"]),
            status=cast(SessionStatus, payload["status"]),
            metadata=dict(cast(dict[str, Any], payload.get("metadata", {}))),
        )


@dataclass(slots=True)
class CoordinationLease:
    lease_id: str
    resource_key: str
    owner_agent_id: str
    owner_session_id: str | None
    status: LeaseStatus
    created_at: str
    renewed_at: str
    expires_at: str
    released_at: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "resource_key": self.resource_key,
            "owner_agent_id": self.owner_agent_id,
            "owner_session_id": self.owner_session_id,
            "status": self.status,
            "created_at": self.created_at,
            "renewed_at": self.renewed_at,
            "expires_at": self.expires_at,
            "released_at": self.released_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CoordinationLease:
        return cls(
            lease_id=str(payload["lease_id"]),
            resource_key=str(payload["resource_key"]),
            owner_agent_id=str(payload["owner_agent_id"]),
            owner_session_id=cast(str | None, payload.get("owner_session_id")),
            status=cast(LeaseStatus, payload["status"]),
            created_at=str(payload["created_at"]),
            renewed_at=str(payload["renewed_at"]),
            expires_at=str(payload["expires_at"]),
            released_at=cast(str | None, payload.get("released_at")),
            reason=cast(str | None, payload.get("reason")),
        )


@dataclass(slots=True)
class HandoffNote:
    handoff_id: str
    created_by: str
    created_at: str
    resource_key: str | None
    summary: str
    next_action: str
    references: list[ResourceReference] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "resource_key": self.resource_key,
            "summary": self.summary,
            "next_action": self.next_action,
            "references": [
                {
                    "type": reference["type"],
                    "value": reference["value"],
                    "label": reference.get("label"),
                }
                for reference in self.references
            ],
            "blocked_by": self.blocked_by,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HandoffNote:
        return cls(
            handoff_id=str(payload["handoff_id"]),
            created_by=str(payload["created_by"]),
            created_at=str(payload["created_at"]),
            resource_key=cast(str | None, payload.get("resource_key")),
            summary=str(payload["summary"]),
            next_action=str(payload["next_action"]),
            references=[
                cast(ResourceReference, dict(reference))
                for reference in cast(list[dict[str, Any]], payload.get("references", []))
            ],
            blocked_by=[str(item) for item in payload.get("blocked_by", [])],
        )


@dataclass(slots=True)
class CoordinationState:
    schema_version: int
    updated_at: str
    sessions: dict[str, AgentSession] = field(default_factory=dict)
    leases: dict[str, CoordinationLease] = field(default_factory=dict)
    handoffs: dict[str, HandoffNote] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "sessions": {
                key: session.to_dict() for key, session in sorted(self.sessions.items())
            },
            "leases": {key: lease.to_dict() for key, lease in sorted(self.leases.items())},
            "handoffs": {
                key: handoff.to_dict() for key, handoff in sorted(self.handoffs.items())
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CoordinationState:
        return cls(
            schema_version=int(payload["schema_version"]),
            updated_at=str(payload["updated_at"]),
            sessions={
                key: AgentSession.from_dict(cast(dict[str, Any], value))
                for key, value in cast(dict[str, Any], payload.get("sessions", {})).items()
            },
            leases={
                key: CoordinationLease.from_dict(cast(dict[str, Any], value))
                for key, value in cast(dict[str, Any], payload.get("leases", {})).items()
            },
            handoffs={
                key: HandoffNote.from_dict(cast(dict[str, Any], value))
                for key, value in cast(dict[str, Any], payload.get("handoffs", {})).items()
            },
        )


def validate_agent_id(agent_id: str) -> str:
    if not agent_id or len(agent_id) > 80 or AGENT_ID_RE.fullmatch(agent_id) is None:
        raise KSError(
            f"invalid agent_id: {agent_id}",
            exit_code=ExitCode.USAGE,
            code="USAGE",
            hint="agent_id must match ^[A-Za-z0-9._@-]+$ and be at most 80 chars",
        )
    return agent_id


def validate_resource_key(resource_key: str) -> str:
    if not resource_key or len(resource_key) > 240:
        raise KSError(
            "resource_key must be 1-240 chars",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )
    if resource_key.startswith("/") or "\\" in resource_key or "../" in resource_key:
        raise KSError(
            f"invalid resource_key: {resource_key}",
            exit_code=ExitCode.USAGE,
            code="USAGE",
            hint="resource_key is an identifier, not a filesystem path",
        )
    if any(ord(char) < 32 for char in resource_key):
        raise KSError("resource_key contains control characters", exit_code=ExitCode.USAGE)
    return resource_key


def normalize_references(references: list[dict[str, Any]] | None) -> list[ResourceReference]:
    normalized: list[ResourceReference] = []
    for reference in references or []:
        reference_type = str(reference.get("type", ""))
        value = str(reference.get("value", ""))
        if reference_type not in {
            "wiki_page",
            "raw_source",
            "graph_node",
            "graph_edge",
            "vector_chunk",
            "lease",
            "handoff",
            "external",
        }:
            raise KSError(
                f"invalid reference type: {reference_type}",
                exit_code=ExitCode.USAGE,
                code="USAGE",
            )
        if not value:
            raise KSError("reference value is required", exit_code=ExitCode.USAGE, code="USAGE")
        normalized.append(
            {
                "type": cast(ReferenceType, reference_type),
                "value": value,
                "label": cast(str | None, reference.get("label")),
            }
        )
    return normalized
