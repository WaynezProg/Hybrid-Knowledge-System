from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_wiki_http_openapi,
    load_wiki_tools_schema,
    validate_wiki_tool_input,
)


@pytest.mark.contract
def test_wiki_synthesis_adapter_contracts_are_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_wiki_tools_schema())
    assert load_wiki_http_openapi()["paths"]["/wiki/synthesize"]["post"]


@pytest.mark.contract
def test_wiki_synthesis_mcp_tool_contract_accepts_preview_and_apply_payloads() -> None:
    validate_wiki_tool_input(
        "hks_wiki_synthesize",
        {
            "source_relpath": "project-atlas.txt",
            "mode": "preview",
            "provider": "fake",
        },
    )
    validate_wiki_tool_input(
        "hks_wiki_synthesize",
        {
            "candidate_artifact_id": "candidate-1",
            "mode": "apply",
            "provider": "fake",
        },
    )


@pytest.mark.contract
def test_wiki_synthesis_mcp_tool_contract_rejects_missing_artifact_reference() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_wiki_tool_input("hks_wiki_synthesize", {"mode": "preview"})
