from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_coordination_ledger_schema,
    load_coordination_summary_schema,
    load_coordination_tools_schema,
    validate_coordination_summary,
    validate_coordination_tool_input,
)
from hks.core.schema import QueryResponse, Trace, TraceStep, validate


@pytest.mark.contract
def test_coordination_schemas_are_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(load_coordination_tools_schema())
    jsonschema.Draft202012Validator.check_schema(load_coordination_summary_schema())
    jsonschema.Draft202012Validator.check_schema(load_coordination_ledger_schema())


@pytest.mark.contract
def test_coordination_tool_contract_accepts_expected_payloads() -> None:
    validate_coordination_tool_input("hks_coord_session", {"action": "start", "agent_id": "a1"})
    validate_coordination_tool_input(
        "hks_coord_lease",
        {"action": "claim", "agent_id": "a1", "resource_key": "wiki:atlas"},
    )
    validate_coordination_tool_input(
        "hks_coord_handoff",
        {
            "action": "add",
            "agent_id": "a1",
            "summary": "done",
            "next_action": "review",
        },
    )
    validate_coordination_tool_input("hks_coord_status", {"include_stale": True})


@pytest.mark.contract
def test_coordination_tool_contract_rejects_bad_agent_id() -> None:
    with pytest.raises(jsonschema.ValidationError):
        validate_coordination_tool_input(
            "hks_coord_session",
            {"action": "start", "agent_id": "bad id"},
        )


@pytest.mark.contract
def test_coordination_summary_detail_accepts_conflict_payload() -> None:
    validate_coordination_summary(
        {
            "operation": "lease.claim",
            "sessions": [],
            "leases": [],
            "handoffs": [],
            "events_appended": 0,
            "conflicts": [
                {
                    "code": "LEASE_CONFLICT",
                    "resource_key": "wiki:atlas",
                    "active_lease_id": "lease-1",
                    "owner_agent_id": "a1",
                }
            ],
            "findings": [],
        }
    )


@pytest.mark.contract
def test_query_response_contract_allows_coordination_summary_step() -> None:
    response = QueryResponse(
        answer="coordination status",
        source=[],
        confidence=1.0,
        trace=Trace(
            route="wiki",
            steps=[
                TraceStep(
                    kind="coordination_summary",
                    detail={
                        "operation": "status",
                        "sessions": [],
                        "leases": [],
                        "handoffs": [],
                        "events_appended": 0,
                        "conflicts": [],
                        "findings": [],
                    },
                )
            ],
        ),
    )

    validate(response.to_dict())
