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
def test_mcp_llm_classify_preview(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_llm_classify",
        {"source_relpath": "project-atlas.txt", "provider": "fake"},
    )

    validate(payload)
    assert payload["trace"]["steps"][0]["kind"] == "llm_extraction_summary"


@pytest.mark.integration
def test_mcp_llm_classify_store(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_llm_classify",
        {"source_relpath": "project-atlas.txt", "mode": "store", "provider": "fake"},
    )

    assert payload["trace"]["steps"][0]["detail"]["artifact"]["artifact_id"]


@pytest.mark.integration
def test_mcp_llm_hosted_provider_without_opt_in_returns_usage(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_llm_classify",
        {"source_relpath": "project-atlas.txt", "provider": "hosted-example"},
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert payload["error"]["exit_code"] == 2
