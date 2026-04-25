from __future__ import annotations

import json

import pytest

from hks.adapters import core
from hks.coordination.models import AgentSession
from hks.coordination.store import CoordinationStore
from hks.core.manifest import utc_now_iso
from hks.errors import KSError


def _init_runtime(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))


def test_store_writes_state_and_appends_events(working_docs, tmp_ks_root) -> None:
    _init_runtime(working_docs)
    store = CoordinationStore()
    state = store.empty_state()
    now = utc_now_iso()
    state.sessions["session-1"] = AgentSession(
        session_id="session-1",
        agent_id="agent-a",
        started_at=now,
        last_seen_at=now,
        metadata={},
    )

    store.save(state)
    store.append_events([{"event_id": "event-1", "event_type": "test"}])

    loaded = store.load()
    assert loaded.sessions["session-1"].agent_id == "agent-a"
    assert (tmp_ks_root / "coordination" / "events.jsonl").read_text(encoding="utf-8")


def test_store_maps_corrupt_state_to_dataerr(working_docs, tmp_ks_root) -> None:
    _init_runtime(working_docs)
    state_path = tmp_ks_root / "coordination" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(KSError) as error_info:
        CoordinationStore().load()

    assert error_info.value.code == "LEDGER_DATAERR"
    assert error_info.value.exit_code == 65


def test_store_rejects_schema_invalid_state(working_docs, tmp_ks_root) -> None:
    _init_runtime(working_docs)
    state_path = tmp_ks_root / "coordination" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(KSError) as error_info:
        CoordinationStore().load()

    assert error_info.value.code == "LEDGER_DATAERR"
