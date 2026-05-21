from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_graphify_http_openapi,
    load_graphify_tools_schema,
    validate_graphify_tool_input,
)

BEARER_AUTH = [{"BearerAuth": []}]


@pytest.mark.contract
def test_graphify_adapter_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_graphify_tools_schema())
    spec = load_graphify_http_openapi()
    assert spec["paths"]["/graphify/build"]["post"]
    assert spec["components"]["securitySchemes"]["BearerAuth"]["scheme"] == "bearer"
    assert spec["paths"]["/graphify/build"]["post"]["security"] == BEARER_AUTH


@pytest.mark.contract
def test_graphify_mcp_tool_contract_accepts_build_payload() -> None:
    validate_graphify_tool_input(
        "hks_graphify_build",
        {
            "mode": "preview",
            "provider": "fake",
            "include_html": True,
            "include_report": True,
            "force_new_run": False,
        },
    )


@pytest.mark.contract
def test_graphify_mcp_tool_contract_rejects_bad_mode() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_graphify_tool_input("hks_graphify_build", {"mode": "apply"})
