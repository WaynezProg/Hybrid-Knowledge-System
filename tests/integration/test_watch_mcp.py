from __future__ import annotations

import json
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from hks.adapters import core
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
def test_mcp_watch_scan(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_watch_scan",
        {"source_roots": [str(working_docs)]},
    )

    assert payload["trace"]["steps"][0]["kind"] == "watch_summary"


@pytest.mark.integration
def test_mcp_watch_status(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    core.hks_watch_scan(source_roots=[str(working_docs)])

    payload = anyio.run(_call_tool, "hks_watch_status", {})

    assert payload["trace"]["steps"][0]["detail"]["operation"] == "status"
