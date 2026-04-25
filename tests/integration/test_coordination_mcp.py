from __future__ import annotations

import json
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from hks.adapters import core
from hks.adapters.mcp_server import create_server
from hks.cli import app


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
def test_mcp_session_lease_handoff_tools(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    session = anyio.run(
        _call_tool,
        "hks_coord_session",
        {"action": "start", "agent_id": "agent-a"},
    )
    lease = anyio.run(
        _call_tool,
        "hks_coord_lease",
        {"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
    )
    handoff = anyio.run(
        _call_tool,
        "hks_coord_handoff",
        {
            "action": "add",
            "agent_id": "agent-a",
            "summary": "done",
            "next_action": "review",
        },
    )

    assert session["trace"]["steps"][0]["kind"] == "coordination_summary"
    assert lease["trace"]["steps"][0]["detail"]["leases"][0]["resource_key"] == "wiki:atlas"
    assert handoff["trace"]["steps"][0]["detail"]["handoffs"][0]["created_by"] == "agent-a"


@pytest.mark.integration
def test_mcp_and_cli_share_same_coordination_ledger(cli_runner, working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    anyio.run(
        _call_tool,
        "hks_coord_lease",
        {"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
    )

    status = cli_runner.invoke(app, ["coord", "status", "--resource-key", "wiki:atlas"])

    assert status.exit_code == 0
    detail = json.loads(status.stdout)["trace"]["steps"][0]["detail"]
    assert detail["leases"][0]["owner_agent_id"] == "agent-a"
