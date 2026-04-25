from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_coordination_tools_schema,
    validate_coordination_tool_input,
)


@pytest.mark.contract
def test_mcp_coordination_tools_schema_is_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_coordination_tools_schema())


@pytest.mark.contract
def test_mcp_coordination_tools_reject_unknown_fields() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_coordination_tool_input(
            "hks_coord_status",
            {"agent_id": "agent-a", "extra": True},
        )


@pytest.mark.contract
def test_mcp_handoff_add_requires_summary_and_next_action() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_coordination_tool_input(
            "hks_coord_handoff",
            {"action": "add", "agent_id": "agent-a"},
        )
