from __future__ import annotations

import json
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app
from hks.adapters.mcp_server import create_server


def _tool_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, CallToolResult):
        assert result.structuredContent is not None
        return dict(result.structuredContent)
    assert isinstance(result, list)
    assert len(result) == 1
    return json.loads(result[0].text)


async def _call_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    server = create_server()
    return _tool_payload(await server.call_tool(name, payload))


@pytest.mark.integration
def test_mcp_coordination_tools_flow(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    session = anyio.run(
        _call_tool,
        "hks_coord_session",
        {"action": "start", "agent_id": "agent-a"},
    )
    assert session["trace"]["steps"][0]["kind"] == "coordination_summary"

    lease = anyio.run(
        _call_tool,
        "hks_coord_lease",
        {"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
    )
    assert lease["trace"]["steps"][0]["detail"]["leases"][0]["resource_key"] == "wiki:atlas"


@pytest.mark.integration
def test_http_coordination_endpoints(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post(
        "/coord/session",
        json={"action": "start", "agent_id": "agent-a"},
    )
    assert response.status_code == 200
    assert response.json()["trace"]["steps"][0]["kind"] == "coordination_summary"

    conflict_a = client.post(
        "/coord/lease",
        json={"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
    )
    conflict_b = client.post(
        "/coord/lease",
        json={"action": "claim", "agent_id": "agent-b", "resource_key": "wiki:atlas"},
    )
    assert conflict_a.status_code == 200
    assert conflict_b.status_code == 500
    assert conflict_b.json()["error"]["code"] == "LEASE_CONFLICT"
