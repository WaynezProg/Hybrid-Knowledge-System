from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_adapter_error_schema,
    load_mcp_tools_schema,
    validate_adapter_error,
    validate_tool_input,
)


@pytest.mark.contract
def test_mcp_and_adapter_error_schemas_are_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(load_mcp_tools_schema())
    jsonschema.Draft202012Validator.check_schema(load_adapter_error_schema())


@pytest.mark.contract
def test_mcp_tool_input_contract_accepts_expected_payloads() -> None:
    validate_tool_input("hks_query", {"question": "Project Atlas summary"})
    validate_tool_input("hks_ingest", {"path": "/tmp/docs", "pptx_notes": "exclude"})
    validate_tool_input(
        "hks_lint",
        {"strict": True, "severity_threshold": "warning", "fix": "plan"},
    )


@pytest.mark.contract
def test_mcp_tool_input_contract_rejects_unknown_fields_and_bad_choices() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_tool_input("hks_query", {"question": "x", "extra": True})

    with pytest.raises(jsonschema.ValidationError):
        validate_tool_input("hks_lint", {"severity_threshold": "fatal"})


@pytest.mark.contract
def test_adapter_error_envelope_contract_accepts_cli_exit_semantics() -> None:
    validate_adapter_error(
        {
            "ok": False,
            "request_id": "req-1",
            "error": {
                "code": "NOINPUT",
                "exit_code": 66,
                "message": "/ks/ 尚未初始化",
                "hint": "run `ks ingest <path>`",
                "details": [],
            },
            "response": None,
        }
    )
