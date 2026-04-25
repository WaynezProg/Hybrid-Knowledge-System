from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hks.coordination.service import CoordinationService
from hks.coordination.store import CoordinationStore
from hks.errors import KSError


def _service(tmp_ks_root) -> CoordinationService:
    return CoordinationService(CoordinationStore())


def _init_runtime(core, working_docs) -> None:
    core.hks_ingest(path=str(working_docs))


def test_service_reuses_active_session(working_docs, tmp_ks_root) -> None:
    from hks.adapters import core

    _init_runtime(core, working_docs)
    service = _service(tmp_ks_root)

    first = service.start_session("agent-a")
    second = service.start_session("agent-a")

    first_id = first.trace.steps[0].detail["sessions"][0]["session_id"]
    second_id = second.trace.steps[0].detail["sessions"][0]["session_id"]
    assert first_id == second_id


def test_service_blocks_conflicting_active_lease(working_docs, tmp_ks_root) -> None:
    from hks.adapters import core

    _init_runtime(core, working_docs)
    service = _service(tmp_ks_root)
    service.claim_lease("agent-a", "wiki:atlas")

    with pytest.raises(KSError) as error_info:
        service.claim_lease("agent-b", "wiki:atlas")

    error = error_info.value
    assert error.code == "LEASE_CONFLICT"
    assert error.response is not None
    assert error.response.trace.steps[0].detail["conflicts"][0]["owner_agent_id"] == "agent-a"


def test_service_lint_reports_missing_handoff_reference(working_docs, tmp_ks_root) -> None:
    from hks.adapters import core

    _init_runtime(core, working_docs)
    service = _service(tmp_ks_root)
    service.add_handoff(
        "agent-a",
        resource_key="wiki:atlas",
        summary="checked",
        next_action="review",
        references=[{"type": "wiki_page", "value": "missing-page", "label": None}],
    )

    response = service.lint()

    findings = response.trace.steps[0].detail["findings"]
    assert findings[0]["category"] == "missing_reference"


def test_service_derives_stale_sessions_from_ttl(working_docs, tmp_ks_root) -> None:
    from hks.adapters import core

    _init_runtime(core, working_docs)
    service = _service(tmp_ks_root)
    response = service.start_session("agent-a")
    session_id = response.trace.steps[0].detail["sessions"][0]["session_id"]

    store = CoordinationStore()
    with store.locked():
        state = store.load()
        state.sessions[session_id].last_seen_at = (
            datetime.now(UTC) - timedelta(hours=2)
        ).isoformat()
        store.save(state)

    stale = service.status(agent_id="agent-a")
    hidden = service.status(agent_id="agent-a", include_stale=False)

    assert stale.trace.steps[0].detail["sessions"][0]["status"] == "stale"
    assert hidden.trace.steps[0].detail["sessions"] == []


def test_service_allows_takeover_after_lease_expiry(working_docs, tmp_ks_root) -> None:
    from hks.adapters import core

    _init_runtime(core, working_docs)
    service = _service(tmp_ks_root)
    first = service.claim_lease("agent-a", "wiki:atlas")
    lease_id = first.trace.steps[0].detail["leases"][0]["lease_id"]

    store = CoordinationStore()
    with store.locked():
        state = store.load()
        state.leases[lease_id].expires_at = (
            datetime.now(UTC) - timedelta(seconds=1)
        ).isoformat()
        store.save(state)

    second = service.claim_lease("agent-b", "wiki:atlas")

    assert second.trace.steps[0].detail["leases"][0]["owner_agent_id"] == "agent-b"
