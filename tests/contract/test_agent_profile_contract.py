from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters.agent_config import AGENT_TOOL_NAMES
from hks.adapters.contracts import validate_catalog_tool_input
from hks.adapters.http_server import create_app
from hks.adapters.mcp_server import (
    create_agent_server,
    create_full_server,
    list_tool_names_for_current_profile,
    tool_names_for_profile,
)

_AGENT_HTTP_HEADERS = {"host": "127.0.0.1", "authorization": "Bearer secret"}


def test_agent_profile_exposes_only_allowlisted_tools() -> None:
    server = create_agent_server()
    tool_names = set(server._tool_manager._tools.keys())  # noqa: SLF001
    assert tool_names == AGENT_TOOL_NAMES


def test_full_profile_includes_agent_tools() -> None:
    names = tool_names_for_profile("full")
    assert "hks_workspace_ingest_session_memory" in names
    assert "hks_session_memory_summary" in names


def test_full_server_has_more_tools_than_agent() -> None:
    full_server = create_full_server()
    agent_server = create_agent_server()
    full_names = set(full_server._tool_manager._tools.keys())  # noqa: SLF001
    agent_names = set(agent_server._tool_manager._tools.keys())  # noqa: SLF001
    assert agent_names < full_names


def test_list_tool_names_for_current_profile_follows_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_AGENT_PROFILE", "1")
    assert list_tool_names_for_current_profile() == sorted(AGENT_TOOL_NAMES)
    monkeypatch.delenv("HKS_AGENT_PROFILE", raising=False)
    full_names = list_tool_names_for_current_profile()
    assert "hks_query" in full_names
    assert "hks_workspace_ingest_session_memory" in full_names


def test_agent_profile_catalog_tool_contract_accepts_workspace_scoped_payloads() -> None:
    validate_catalog_tool_input(
        "hks_workspace_ingest_session_memory",
        {"workspace_id": "hks", "path": "daily/2026-05-31.md"},
    )
    validate_catalog_tool_input(
        "hks_session_memory_summary",
        {
            "workspace_id": "hks",
            "date_from": "2026-05-31",
            "date_to": "2026-05-31",
        },
    )
    validate_catalog_tool_input(
        "hks_source_list",
        {"workspace_id": "hks", "relpath_query": "daily"},
    )


@pytest.mark.parametrize(
    "path",
    [
        "/query",
        "/ingest",
        "/graphify/build",
        "/catalog/sources",
    ],
)
def test_agent_profile_http_forbids_full_routes(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setenv("HKS_AGENT_PROFILE", "1")
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    client = TestClient(create_app())
    response = client.post(path, json={}, headers=_AGENT_HTTP_HEADERS)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_PROFILE_FORBIDDEN"
