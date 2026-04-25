"""Command wrappers for multi-agent coordination."""

from __future__ import annotations

from typing import Any, Literal, cast

from hks.coordination.models import normalize_references
from hks.coordination.service import DEFAULT_TTL_SECONDS, CoordinationService
from hks.core.schema import QueryResponse

type SessionAction = Literal["start", "heartbeat", "close"]
type LeaseAction = Literal["claim", "renew", "release"]
type HandoffAction = Literal["add", "list"]


def run_session(
    *,
    action: SessionAction,
    agent_id: str,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> QueryResponse:
    service = CoordinationService()
    if action == "start":
        return service.start_session(agent_id, metadata)
    if action == "heartbeat":
        return service.heartbeat(agent_id, session_id)
    return service.close_session(agent_id, session_id)


def run_lease(
    *,
    action: LeaseAction,
    agent_id: str,
    resource_key: str,
    session_id: str | None = None,
    lease_id: str | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    reason: str | None = None,
) -> QueryResponse:
    service = CoordinationService()
    if action == "claim":
        return service.claim_lease(
            agent_id,
            resource_key,
            session_id=session_id,
            ttl_seconds=ttl_seconds,
            reason=reason,
        )
    if action == "renew":
        return service.renew_lease(
            agent_id,
            resource_key,
            lease_id=lease_id,
            ttl_seconds=ttl_seconds,
            reason=reason,
        )
    return service.release_lease(agent_id, resource_key, lease_id=lease_id)


def run_handoff(
    *,
    action: HandoffAction,
    agent_id: str,
    resource_key: str | None = None,
    summary: str | None = None,
    next_action: str | None = None,
    references: list[dict[str, Any]] | None = None,
    blocked_by: list[str] | None = None,
) -> QueryResponse:
    service = CoordinationService()
    if action == "list":
        return service.list_handoffs(agent_id=agent_id, resource_key=resource_key)
    return service.add_handoff(
        agent_id,
        resource_key=resource_key,
        summary=summary or "",
        next_action=next_action or "",
        references=normalize_references(references),
        blocked_by=blocked_by or [],
    )


def run_status(
    *,
    agent_id: str | None = None,
    resource_key: str | None = None,
    include_stale: bool = True,
) -> QueryResponse:
    return CoordinationService().status(
        agent_id=agent_id,
        resource_key=resource_key,
        include_stale=include_stale,
    )


def run_lint() -> QueryResponse:
    return CoordinationService().lint()


def parse_references_json(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [cast(dict[str, Any], item) for item in value]
    raise TypeError("references must be a JSON array")
