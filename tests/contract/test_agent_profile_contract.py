from __future__ import annotations

from hks.adapters.agent_config import AGENT_TOOL_NAMES
from hks.adapters.mcp_server import create_agent_server, create_full_server, tool_names_for_profile


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
