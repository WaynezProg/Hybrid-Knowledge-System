from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_watch_http_openapi,
    load_watch_tools_schema,
    validate_watch_tool_input,
)


@pytest.mark.contract
def test_watch_adapter_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_watch_tools_schema())
    paths = load_watch_http_openapi()["paths"]
    assert paths["/watch/scan"]["post"]
    assert paths["/watch/run"]["post"]
    assert paths["/watch/status"]["post"]


@pytest.mark.contract
def test_watch_mcp_tool_contract_accepts_payloads() -> None:
    validate_watch_tool_input("hks_watch_scan", {"source_roots": ["/tmp/docs"]})
    validate_watch_tool_input(
        "hks_watch_run",
        {
            "source_roots": ["/tmp/docs"],
            "mode": "execute",
            "profile": "ingest-only",
            "prune": False,
            "include_graphify": False,
        },
    )
    validate_watch_tool_input("hks_watch_status", {})


@pytest.mark.contract
def test_watch_mcp_tool_contract_rejects_bad_mode() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_watch_tool_input("hks_watch_run", {"mode": "apply"})
