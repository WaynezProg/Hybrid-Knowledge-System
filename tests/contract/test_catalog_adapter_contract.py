from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_catalog_http_openapi,
    load_catalog_tools_schema,
    validate_catalog_tool_input,
)


def test_catalog_adapter_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_catalog_tools_schema())
    paths = load_catalog_http_openapi()["paths"]
    assert paths["/catalog/sources"]["post"]
    assert paths["/catalog/sources/{relpath}"]["post"]
    assert paths["/workspaces"]["post"]
    assert paths["/workspaces/{workspace_id}"]["post"]
    assert paths["/workspaces/{workspace_id}/query"]["post"]


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


def test_catalog_mcp_tool_contract_rejects_bad_workspace_id() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_catalog_tool_input(
            "hks_workspace_register",
            {"workspace_id": "../bad", "ks_root": "/tmp/ks"},
        )

