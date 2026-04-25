"""Coordination service operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jsonschema

from hks.adapters.contracts import validate_coordination_summary
from hks.coordination.models import (
    AgentSession,
    CoordinationConflict,
    CoordinationEvent,
    CoordinationFinding,
    CoordinationLease,
    CoordinationState,
    HandoffNote,
    ResourceReference,
    validate_agent_id,
    validate_resource_key,
)
from hks.coordination.store import CoordinationStore
from hks.core.manifest import utc_now_iso
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError

DEFAULT_TTL_SECONDS = 1800


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now() -> datetime:
    return datetime.now(UTC)


def _to_iso(value: datetime) -> str:
    return value.isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _event(kind: str, payload: dict[str, Any]) -> CoordinationEvent:
    return {
        "event_id": _id("event"),
        "event_type": kind,
        "created_at": utc_now_iso(),
        "payload": payload,
    }


def _fresh_session(session: AgentSession, *, at: datetime, ttl_seconds: int) -> AgentSession:
    if session.status != "active":
        return session
    if _parse_time(session.last_seen_at) + timedelta(seconds=ttl_seconds) >= at:
        return session
    return AgentSession(
        session_id=session.session_id,
        agent_id=session.agent_id,
        started_at=session.started_at,
        last_seen_at=session.last_seen_at,
        status="stale",
        metadata=session.metadata,
    )


def _summary_response(
    answer: str,
    *,
    operation: str,
    sessions: list[AgentSession] | None = None,
    leases: list[CoordinationLease] | None = None,
    handoffs: list[HandoffNote] | None = None,
    events_appended: int = 0,
    conflicts: list[CoordinationConflict] | None = None,
    findings: list[CoordinationFinding] | None = None,
) -> QueryResponse:
    detail = {
        "operation": operation,
        "sessions": [session.to_dict() for session in sessions or []],
        "leases": [lease.to_dict() for lease in leases or []],
        "handoffs": [handoff.to_dict() for handoff in handoffs or []],
        "events_appended": events_appended,
        "conflicts": conflicts or [],
        "findings": findings or [],
    }
    validate_coordination_summary(detail)
    return QueryResponse(
        answer=answer,
        source=[],
        confidence=1.0,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="coordination_summary", detail=detail)],
        ),
    )


class CoordinationService:
    def __init__(self, store: CoordinationStore | None = None) -> None:
        self.store = store or CoordinationStore()

    def start_session(self, agent_id: str, metadata: dict[str, Any] | None = None) -> QueryResponse:
        validate_agent_id(agent_id)
        with self.store.locked():
            state = self.store.load()
            session = self._active_session_for_agent(state, agent_id)
            event_count = 0
            if session is None:
                now = utc_now_iso()
                session = AgentSession(
                    session_id=_id("session"),
                    agent_id=agent_id,
                    started_at=now,
                    last_seen_at=now,
                    metadata=metadata or {},
                )
                state.sessions[session.session_id] = session
                events = [_event("session_started", session.to_dict())]
                self.store.append_events(events)
                event_count = len(events)
            else:
                session.last_seen_at = utc_now_iso()
                if metadata:
                    session.metadata.update(metadata)
            self.store.save(state)
        return _summary_response(
            f"agent {agent_id} session active",
            operation="session.start",
            sessions=[session],
            events_appended=event_count,
        )

    def heartbeat(self, agent_id: str, session_id: str | None = None) -> QueryResponse:
        validate_agent_id(agent_id)
        with self.store.locked():
            state = self.store.load()
            session = self._find_session(state, agent_id, session_id)
            if session is None:
                raise KSError(
                    "session not found",
                    exit_code=ExitCode.NOINPUT,
                    code="SESSION_NOT_FOUND",
                )
            session.last_seen_at = utc_now_iso()
            session.status = "active"
            self.store.save(state)
            event = _event("session_heartbeat", session.to_dict())
            self.store.append_events([event])
        return _summary_response(
            f"agent {agent_id} heartbeat recorded",
            operation="session.heartbeat",
            sessions=[session],
            events_appended=1,
        )

    def close_session(self, agent_id: str, session_id: str | None = None) -> QueryResponse:
        validate_agent_id(agent_id)
        with self.store.locked():
            state = self.store.load()
            session = self._find_session(state, agent_id, session_id)
            if session is None:
                raise KSError(
                    "session not found",
                    exit_code=ExitCode.NOINPUT,
                    code="SESSION_NOT_FOUND",
                )
            session.status = "closed"
            session.last_seen_at = utc_now_iso()
            self.store.save(state)
            event = _event("session_closed", session.to_dict())
            self.store.append_events([event])
        return _summary_response(
            f"agent {agent_id} session closed",
            operation="session.close",
            sessions=[session],
            events_appended=1,
        )

    def claim_lease(
        self,
        agent_id: str,
        resource_key: str,
        *,
        session_id: str | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        reason: str | None = None,
    ) -> QueryResponse:
        validate_agent_id(agent_id)
        validate_resource_key(resource_key)
        _validate_ttl(ttl_seconds)
        with self.store.locked():
            state = self.store.load()
            events = self._expire_leases(state, _now())
            active = self._active_lease_for_resource(state, resource_key)
            if active is not None and active.owner_agent_id != agent_id:
                conflict: CoordinationConflict = {
                    "code": "LEASE_CONFLICT",
                    "resource_key": resource_key,
                    "active_lease_id": active.lease_id,
                    "owner_agent_id": active.owner_agent_id,
                }
                response = _summary_response(
                    f"{resource_key} is already leased by {active.owner_agent_id}",
                    operation="lease.claim",
                    leases=[active],
                    events_appended=0,
                    conflicts=[conflict],
                )
                raise KSError(
                    response.answer,
                    exit_code=ExitCode.GENERAL,
                    code="LEASE_CONFLICT",
                    response=response,
                )
            if active is None:
                now = _now()
                lease = CoordinationLease(
                    lease_id=_id("lease"),
                    resource_key=resource_key,
                    owner_agent_id=agent_id,
                    owner_session_id=session_id,
                    status="active",
                    created_at=_to_iso(now),
                    renewed_at=_to_iso(now),
                    expires_at=_to_iso(now + timedelta(seconds=ttl_seconds)),
                    reason=reason,
                )
                state.leases[lease.lease_id] = lease
                events.append(_event("lease_claimed", lease.to_dict()))
            else:
                lease = active
                now = _now()
                lease.renewed_at = _to_iso(now)
                lease.expires_at = _to_iso(now + timedelta(seconds=ttl_seconds))
                lease.reason = reason or lease.reason
                events.append(_event("lease_renewed", lease.to_dict()))
            self.store.save(state)
            self.store.append_events(events)
        return _summary_response(
            f"{resource_key} lease active",
            operation="lease.claim",
            leases=[lease],
            events_appended=len(events),
        )

    def renew_lease(
        self,
        agent_id: str,
        resource_key: str,
        *,
        lease_id: str | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        reason: str | None = None,
    ) -> QueryResponse:
        validate_agent_id(agent_id)
        validate_resource_key(resource_key)
        _validate_ttl(ttl_seconds)
        with self.store.locked():
            state = self.store.load()
            events = self._expire_leases(state, _now())
            lease = self._find_lease(state, resource_key, lease_id)
            if lease is None or lease.status != "active":
                raise KSError(
                    "active lease not found",
                    exit_code=ExitCode.NOINPUT,
                    code="LEASE_NOT_FOUND",
                )
            self._assert_lease_owner(lease, agent_id)
            now = _now()
            lease.renewed_at = _to_iso(now)
            lease.expires_at = _to_iso(now + timedelta(seconds=ttl_seconds))
            lease.reason = reason or lease.reason
            events.append(_event("lease_renewed", lease.to_dict()))
            self.store.save(state)
            self.store.append_events(events)
        return _summary_response(
            f"{resource_key} lease renewed",
            operation="lease.renew",
            leases=[lease],
            events_appended=len(events),
        )

    def release_lease(
        self,
        agent_id: str,
        resource_key: str,
        *,
        lease_id: str | None = None,
    ) -> QueryResponse:
        validate_agent_id(agent_id)
        validate_resource_key(resource_key)
        with self.store.locked():
            state = self.store.load()
            lease = self._find_lease(state, resource_key, lease_id)
            if lease is None or lease.status != "active":
                raise KSError(
                    "active lease not found",
                    exit_code=ExitCode.NOINPUT,
                    code="LEASE_NOT_FOUND",
                )
            self._assert_lease_owner(lease, agent_id)
            lease.status = "released"
            lease.released_at = utc_now_iso()
            event = _event("lease_released", lease.to_dict())
            self.store.save(state)
            self.store.append_events([event])
        return _summary_response(
            f"{resource_key} lease released",
            operation="lease.release",
            leases=[lease],
            events_appended=1,
        )

    def add_handoff(
        self,
        agent_id: str,
        *,
        resource_key: str | None,
        summary: str,
        next_action: str,
        references: list[ResourceReference] | None = None,
        blocked_by: list[str] | None = None,
    ) -> QueryResponse:
        validate_agent_id(agent_id)
        if resource_key is not None:
            validate_resource_key(resource_key)
        if not summary or not next_action:
            raise KSError(
                "summary and next_action are required",
                exit_code=ExitCode.USAGE,
                code="USAGE",
            )
        with self.store.locked():
            state = self.store.load()
            handoff = HandoffNote(
                handoff_id=_id("handoff"),
                created_by=agent_id,
                created_at=utc_now_iso(),
                resource_key=resource_key,
                summary=summary,
                next_action=next_action,
                references=references or [],
                blocked_by=blocked_by or [],
            )
            state.handoffs[handoff.handoff_id] = handoff
            event = _event("handoff_added", handoff.to_dict())
            self.store.save(state)
            self.store.append_events([event])
        return _summary_response(
            "handoff recorded",
            operation="handoff.add",
            handoffs=[handoff],
            events_appended=1,
        )

    def list_handoffs(
        self,
        *,
        agent_id: str | None = None,
        resource_key: str | None = None,
    ) -> QueryResponse:
        if agent_id is not None:
            validate_agent_id(agent_id)
        if resource_key is not None:
            validate_resource_key(resource_key)
        state = self.store.load()
        handoffs = [
            handoff
            for handoff in state.handoffs.values()
            if (agent_id is None or handoff.created_by == agent_id)
            and (resource_key is None or handoff.resource_key == resource_key)
        ]
        return _summary_response(
            f"{len(handoffs)} handoff(s)",
            operation="handoff.list",
            handoffs=handoffs,
        )

    def status(
        self,
        *,
        agent_id: str | None = None,
        resource_key: str | None = None,
        include_stale: bool = True,
    ) -> QueryResponse:
        if agent_id is not None:
            validate_agent_id(agent_id)
        if resource_key is not None:
            validate_resource_key(resource_key)
        state = self.store.load()
        now = _now()
        sessions = [
            _fresh_session(session, at=now, ttl_seconds=DEFAULT_TTL_SECONDS)
            for session in state.sessions.values()
            if agent_id is None or session.agent_id == agent_id
        ]
        if not include_stale:
            sessions = [session for session in sessions if session.status != "stale"]
        leases = [
            self._view_lease(lease, now)
            for lease in state.leases.values()
            if resource_key is None or lease.resource_key == resource_key
        ]
        handoffs = [
            handoff
            for handoff in state.handoffs.values()
            if (agent_id is None or handoff.created_by == agent_id)
            and (resource_key is None or handoff.resource_key == resource_key)
        ]
        return _summary_response(
            "coordination status",
            operation="status",
            sessions=sessions,
            leases=leases,
            handoffs=handoffs,
        )

    def lint(self) -> QueryResponse:
        from hks.coordination.lint import run_coordination_lint

        state = self.store.load()
        findings = run_coordination_lint(state, self.store.paths)
        return _summary_response(
            "coordination lint complete",
            operation="lint",
            findings=findings,
        )

    def _active_session_for_agent(
        self,
        state: CoordinationState,
        agent_id: str,
    ) -> AgentSession | None:
        for session in state.sessions.values():
            if session.agent_id == agent_id and session.status == "active":
                return session
        return None

    def _find_session(
        self,
        state: CoordinationState,
        agent_id: str,
        session_id: str | None,
    ) -> AgentSession | None:
        if session_id is not None:
            session = state.sessions.get(session_id)
            if session is not None and session.agent_id == agent_id:
                return session
            return None
        return self._active_session_for_agent(state, agent_id)

    def _active_lease_for_resource(
        self,
        state: CoordinationState,
        resource_key: str,
    ) -> CoordinationLease | None:
        for lease in state.leases.values():
            if lease.resource_key == resource_key and lease.status == "active":
                return lease
        return None

    def _find_lease(
        self,
        state: CoordinationState,
        resource_key: str,
        lease_id: str | None,
    ) -> CoordinationLease | None:
        if lease_id is not None:
            lease = state.leases.get(lease_id)
            if lease is not None and lease.resource_key == resource_key:
                return lease
            return None
        return self._active_lease_for_resource(state, resource_key)

    def _assert_lease_owner(self, lease: CoordinationLease, agent_id: str) -> None:
        if lease.owner_agent_id == agent_id:
            return
        conflict: CoordinationConflict = {
            "code": "LEASE_CONFLICT",
            "resource_key": lease.resource_key,
            "active_lease_id": lease.lease_id,
            "owner_agent_id": lease.owner_agent_id,
        }
        response = _summary_response(
            f"{lease.resource_key} is leased by {lease.owner_agent_id}",
            operation="lease",
            leases=[lease],
            conflicts=[conflict],
        )
        raise KSError(response.answer, code="LEASE_CONFLICT", response=response)

    def _expire_leases(
        self,
        state: CoordinationState,
        at: datetime,
    ) -> list[CoordinationEvent]:
        events: list[CoordinationEvent] = []
        for lease in state.leases.values():
            if lease.status == "active" and _parse_time(lease.expires_at) <= at:
                lease.status = "expired"
                events.append(_event("lease_expired", lease.to_dict()))
        return events

    def _view_lease(self, lease: CoordinationLease, at: datetime) -> CoordinationLease:
        if lease.status != "active" or _parse_time(lease.expires_at) > at:
            return lease
        return CoordinationLease(
            lease_id=lease.lease_id,
            resource_key=lease.resource_key,
            owner_agent_id=lease.owner_agent_id,
            owner_session_id=lease.owner_session_id,
            status="expired",
            created_at=lease.created_at,
            renewed_at=lease.renewed_at,
            expires_at=lease.expires_at,
            released_at=lease.released_at,
            reason=lease.reason,
        )


def _validate_ttl(ttl_seconds: int) -> None:
    if ttl_seconds < 1 or ttl_seconds > 86400:
        raise KSError(
            "ttl_seconds must be between 1 and 86400",
            exit_code=ExitCode.USAGE,
            code="USAGE",
        )


def validate_summary_contract(payload: dict[str, Any]) -> None:
    try:
        validate_coordination_summary(payload)
    except jsonschema.ValidationError as error:
        raise AssertionError(str(error)) from error
