from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_catalog_http_openapi,
    load_catalog_tools_schema,
    validate_catalog_tool_input,
)

BEARER_AUTH = [{"BearerAuth": []}]
CATALOG_SOURCE_OPERATIONS = {
    "/catalog/sources",
    "/catalog/sources/{relpath}",
}
WORKSPACE_OPERATIONS = {
    "/workspaces",
    "/workspaces/{workspace_id}",
    "/workspaces/{workspace_id}/query",
    "/workspaces/{workspace_id}/ingest/session-memory",
    "/workspaces/{workspace_id}/catalog/sources",
    "/session-memory/summary",
}


def test_catalog_adapter_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_catalog_tools_schema())
    spec = load_catalog_http_openapi()
    paths = spec["paths"]
    assert paths["/catalog/sources"]["post"]
    assert paths["/catalog/sources/{relpath}"]["post"]
    assert paths["/workspaces"]["post"]
    assert paths["/workspaces/{workspace_id}"]["post"]
    assert paths["/workspaces/{workspace_id}/query"]["post"]
    assert paths["/workspaces/{workspace_id}/ingest/session-memory"]["post"]
    assert paths["/workspaces/{workspace_id}/catalog/sources"]["post"]
    assert paths["/session-memory/summary"]["post"]
    assert spec["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"

    for path in WORKSPACE_OPERATIONS:
        assert paths[path]["post"]["security"] == BEARER_AUTH

    for path in CATALOG_SOURCE_OPERATIONS:
        assert "security" not in paths[path]["post"]


def test_catalog_mcp_tool_contract_accepts_payloads() -> None:
    validate_catalog_tool_input("hks_source_list", {"ks_root": "/tmp/ks", "format": "txt"})
    validate_catalog_tool_input("hks_source_show", {"relpath": "project-atlas.txt"})
    validate_catalog_tool_input("hks_workspace_list", {"registry_path": "/tmp/workspaces.json"})
    validate_catalog_tool_input(
        "hks_workspace_register",
        {"workspace_id": "proj-a", "ks_root": "/tmp/ks", "tags": ["demo"]},
    )
    validate_catalog_tool_input(
        "hks_workspace_query",
        {"workspace_id": "proj-a", "question": "重點", "writeback": "no"},
    )
    validate_catalog_tool_input(
        "hks_workspace_ingest_session_memory",
        {"workspace_id": "proj-a", "path": "daily/2026-05-31.md"},
    )
    validate_catalog_tool_input(
        "hks_session_memory_summary",
        {
            "workspace_id": "proj-a",
            "date_from": "2026-05-31",
            "date_to": "2026-05-31",
        },
    )
    validate_catalog_tool_input(
        "hks_source_list",
        {"workspace_id": "proj-a", "limit": 10},
    )


def test_catalog_mcp_tool_contract_rejects_bad_workspace_id() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_catalog_tool_input(
            "hks_workspace_register",
            {"workspace_id": "../bad", "ks_root": "/tmp/ks"},
        )
