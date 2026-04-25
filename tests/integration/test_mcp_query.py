from __future__ import annotations

import json
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from hks.adapters import core
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
def test_mcp_query_matches_core_route_and_source(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    core_payload = core.hks_query(question="Project Atlas summary", writeback="no")

    mcp_payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary"},
    )

    validate(mcp_payload)
    assert mcp_payload["trace"]["route"] == core_payload["trace"]["route"]
    assert mcp_payload["source"] == core_payload["source"]
    assert "ok" not in mcp_payload


@pytest.mark.integration
def test_mcp_query_noinput_returns_adapter_error_envelope() -> None:
    payload = anyio.run(_call_tool, "hks_query", {"question": "Project Atlas summary"})

    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOINPUT"
    assert payload["error"]["exit_code"] == 66
    assert payload["response"]["trace"]["steps"][0]["kind"] == "error"


@pytest.mark.integration
def test_mcp_query_invalid_writeback_returns_usage_envelope() -> None:
    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary", "writeback": "later"},
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert payload["error"]["exit_code"] == 2
    assert "writeback" in payload["error"]["message"]


@pytest.mark.integration
def test_mcp_query_default_does_not_write_back_pages(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    pages = tmp_ks_root / "wiki" / "pages"
    before = sorted(path.name for path in pages.glob("*.md"))

    payload = anyio.run(_call_tool, "hks_query", {"question": "Project Atlas summary"})

    assert payload["source"] == ["wiki"]
    assert sorted(path.name for path in pages.glob("*.md")) == before
