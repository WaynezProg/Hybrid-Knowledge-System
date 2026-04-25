from __future__ import annotations

import json
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from hks.adapters import core
from hks.adapters.mcp_server import create_server
from hks.core.lock import acquire_lock
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
def test_mcp_ingest_creates_runtime_artifacts(working_docs, tmp_ks_root) -> None:
    payload = anyio.run(_call_tool, "hks_ingest", {"path": str(working_docs)})

    validate(payload)
    assert payload["trace"]["steps"][0]["kind"] == "ingest_summary"
    assert (tmp_ks_root / "manifest.json").exists()
    assert (tmp_ks_root / "wiki" / "index.md").exists()
    assert (tmp_ks_root / "graph" / "graph.json").exists()
    assert (tmp_ks_root / "vector" / "db").exists()
    assert list((tmp_ks_root / "raw_sources").glob("*.txt"))


@pytest.mark.integration
def test_mcp_lint_clean_runtime_and_strict_error(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))

    clean = anyio.run(_call_tool, "hks_lint", {})
    validate(clean)
    assert clean["trace"]["steps"][0]["kind"] == "lint_summary"
    assert clean["trace"]["steps"][0]["detail"]["findings"] == []

    next((tmp_ks_root / "raw_sources").glob("*.txt")).unlink()
    strict = anyio.run(
        _call_tool,
        "hks_lint",
        {"strict": True, "severity_threshold": "error"},
    )
    assert strict["ok"] is False
    assert strict["error"]["code"] == "LINT_FAILED"
    assert strict["response"]["trace"]["steps"][0]["kind"] == "lint_summary"


@pytest.mark.integration
def test_mcp_ingest_lock_contention_returns_adapter_error(working_docs, tmp_ks_root) -> None:
    tmp_ks_root.mkdir(parents=True, exist_ok=True)
    handle = acquire_lock(tmp_ks_root / ".lock")
    try:
        payload = anyio.run(_call_tool, "hks_ingest", {"path": str(working_docs)})
    finally:
        handle.close()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "LOCKED"
    assert payload["error"]["exit_code"] == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    ("tool", "payload", "field"),
    [
        ("hks_ingest", {"path": "/tmp/source", "pptx_notes": "all"}, "pptx_notes"),
        ("hks_lint", {"severity_threshold": "fatal"}, "severity_threshold"),
        ("hks_lint", {"fix": "force"}, "fix"),
    ],
)
def test_mcp_ingest_lint_usage_errors(tool: str, payload: dict[str, Any], field: str) -> None:
    response = anyio.run(_call_tool, tool, payload)

    assert response["ok"] is False
    assert response["error"]["code"] == "USAGE"
    assert response["error"]["exit_code"] == 2
    assert field in response["error"]["message"]
