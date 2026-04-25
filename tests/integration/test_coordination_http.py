from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


@pytest.mark.integration
def test_http_coordination_endpoints_use_adapter_error_envelope(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    session = client.post("/coord/session", json={"action": "start", "agent_id": "agent-a"})
    first = client.post(
        "/coord/lease",
        json={"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
    )
    second = client.post(
        "/coord/lease",
        json={"action": "claim", "agent_id": "agent-b", "resource_key": "wiki:atlas"},
    )

    assert session.status_code == 200
    assert first.status_code == 200
    assert second.status_code == 500
    assert second.json()["ok"] is False
    assert second.json()["error"]["code"] == "LEASE_CONFLICT"
