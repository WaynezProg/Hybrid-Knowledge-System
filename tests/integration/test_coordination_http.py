from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


@pytest.mark.integration
def test_http_coordination_endpoints_use_adapter_error_envelope(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    session = client.post(
        "/coord/session",
        json={"action": "start", "agent_id": "agent-a"},
        headers=_headers("secret"),
    )
    first = client.post(
        "/coord/lease",
        json={"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
        headers=_headers("secret"),
    )
    second = client.post(
        "/coord/lease",
        json={"action": "claim", "agent_id": "agent-b", "resource_key": "wiki:atlas"},
        headers=_headers("secret"),
    )

    assert session.status_code == 200
    assert first.status_code == 200
    assert second.status_code == 500
    assert second.json()["ok"] is False
    assert second.json()["error"]["code"] == "LEASE_CONFLICT"
