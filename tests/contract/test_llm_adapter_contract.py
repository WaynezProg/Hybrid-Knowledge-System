from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_llm_http_openapi,
    load_llm_tools_schema,
    validate_llm_tool_input,
)


@pytest.mark.contract
def test_llm_adapter_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_llm_tools_schema())
    assert load_llm_http_openapi()["paths"]["/llm/classify"]["post"]


@pytest.mark.contract
def test_llm_mcp_tool_contract_accepts_expected_payload() -> None:
    validate_llm_tool_input(
        "hks_llm_classify",
        {
            "source_relpath": "project-atlas.txt",
            "mode": "preview",
            "provider": "fake",
            "force_new_run": False,
        },
    )


@pytest.mark.contract
def test_llm_mcp_tool_contract_rejects_bad_mode() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_llm_tool_input(
            "hks_llm_classify",
            {"source_relpath": "project-atlas.txt", "mode": "apply"},
        )
