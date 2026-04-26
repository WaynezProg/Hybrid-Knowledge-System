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
    return json.loads(result[0].text)


async def _call_tool(payload: dict[str, Any]) -> dict[str, Any]:
    return _tool_payload(await create_server().call_tool("hks_llm_classify", payload))


def _detail(payload: dict[str, Any]) -> dict[str, Any]:
    detail = dict(payload["trace"]["steps"][0]["detail"])
    detail["provider"] = dict(detail["provider"])
    detail["provider"]["generated_at"] = "<dynamic>"
    return detail


@pytest.mark.integration
def test_llm_cli_mcp_http_details_are_semantically_equivalent(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    cli_payload = core.hks_llm_classify(source_relpath="project-atlas.txt")
    mcp_payload = anyio.run(_call_tool, {"source_relpath": "project-atlas.txt"})
    http_payload = TestClient(create_app()).post(
        "/llm/classify",
        json={"source_relpath": "project-atlas.txt"},
    ).json()

    assert _detail(cli_payload) == _detail(mcp_payload) == _detail(http_payload)
