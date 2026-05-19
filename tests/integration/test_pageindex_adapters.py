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
from hks.core.schema import validate


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
def test_pageindex_core_mcp_http_show_are_equivalent(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    core_payload = core.hks_pageindex_show(source_relpath="project-atlas.txt")
    mcp_payload = anyio.run(
        _call_tool,
        "hks_pageindex_show",
        {"source_relpath": "project-atlas.txt"},
    )
    http_payload = TestClient(create_app()).get("/pageindex/project-atlas.txt").json()

    validate(core_payload)
    assert core_payload["trace"]["steps"][0]["kind"] == "pageindex_summary"
    assert (
        core_payload["trace"]["steps"][0]["detail"]["tree"]
        == mcp_payload["trace"]["steps"][0]["detail"]["tree"]
        == http_payload["trace"]["steps"][0]["detail"]["tree"]
    )


@pytest.mark.integration
def test_pageindex_enrich_adapters_validate_choices(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_pageindex_enrich",
        {"source_relpath": "project-atlas.txt", "mode": "apply"},
    )
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert "mode" in payload["error"]["message"]

    response = TestClient(create_app()).post(
        "/pageindex/enrich",
        json={"source_relpath": "project-atlas.txt", "provider": "unknown"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "USAGE"
