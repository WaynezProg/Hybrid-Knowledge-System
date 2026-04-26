from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_watch_latest_schema,
    load_watch_plan_schema,
    load_watch_run_schema,
    load_watch_summary_schema,
    validate_watch_latest,
    validate_watch_plan,
    validate_watch_run,
    validate_watch_summary,
)
from hks.core.schema import QueryResponse, Trace, TraceStep, validate


def _source_counts() -> dict[str, int]:
    return {
        "unchanged": 0,
        "stale": 1,
        "new": 0,
        "missing": 0,
        "unsupported": 0,
        "corrupt": 0,
    }


def _action_counts() -> dict[str, int]:
    return {"planned": 1, "skipped": 0, "running": 0, "completed": 0, "failed": 0}


def _summary() -> dict[str, object]:
    return {
        "kind": "watch_summary",
        "operation": "scan",
        "mode": "dry-run",
        "profile": "scan-only",
        "plan_id": "plan-1",
        "run_id": None,
        "plan_fingerprint": "fingerprint",
        "source_counts": _source_counts(),
        "action_counts": _action_counts(),
        "artifacts": {"plan": "/tmp/plan.json", "run": None, "latest": "/tmp/latest.json"},
        "idempotent_reuse": False,
        "confidence": 1.0,
    }


def _action() -> dict[str, object]:
    return {
        "action_id": "ingest:a.md",
        "kind": "ingest",
        "source_relpath": "a.md",
        "depends_on": [],
        "status": "planned",
        "input_fingerprint": "sha",
        "output_refs": [],
        "error": None,
    }


@pytest.mark.contract
def test_watch_schemas_are_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(load_watch_summary_schema())
    jsonschema.Draft202012Validator.check_schema(load_watch_plan_schema())
    jsonschema.Draft202012Validator.check_schema(load_watch_run_schema())
    jsonschema.Draft202012Validator.check_schema(load_watch_latest_schema())


@pytest.mark.contract
def test_watch_summary_detail_contract_accepts_expected_payload() -> None:
    validate_watch_summary(_summary())


@pytest.mark.contract
def test_watch_plan_contract_requires_artifact_counts() -> None:
    validate_watch_plan(
        {
            "schema_version": "1.0",
            "plan_id": "plan-1",
            "created_at": "2026-04-26T00:00:00+00:00",
            "plan_fingerprint": "fingerprint",
            "mode": "dry-run",
            "profile": "scan-only",
            "source_counts": _source_counts(),
            "artifact_counts": {
                "llm_extraction_stale": 1,
                "wiki_candidate_stale": 0,
                "graphify_stale": 0,
                "orphaned": 0,
            },
            "actions": [_action()],
            "issues": [],
        }
    )


@pytest.mark.contract
def test_watch_run_and_latest_contracts_accept_expected_payloads() -> None:
    validate_watch_run(
        {
            "schema_version": "1.0",
            "run_id": "run-1",
            "created_at": "2026-04-26T00:00:00+00:00",
            "completed_at": "2026-04-26T00:00:01+00:00",
            "status": "completed",
            "plan_id": "plan-1",
            "plan_fingerprint": "fingerprint",
            "mode": "execute",
            "profile": "ingest-only",
            "requested_by": None,
            "actions": [{**_action(), "status": "completed", "output_refs": ["a.md"]}],
            "summary": {
                **_summary(),
                "operation": "run",
                "mode": "execute",
                "profile": "ingest-only",
                "run_id": "run-1",
                "action_counts": {
                    "planned": 0,
                    "skipped": 0,
                    "running": 0,
                    "completed": 1,
                    "failed": 0,
                },
            },
        }
    )
    validate_watch_latest(
        {
            "schema_version": "1.0",
            "latest_plan_id": "plan-1",
            "latest_run_id": "run-1",
            "updated_at": "2026-04-26T00:00:01+00:00",
            "plan_fingerprint": "fingerprint",
        }
    )


@pytest.mark.contract
def test_query_response_contract_allows_watch_summary_step() -> None:
    response = QueryResponse(
        answer="watch scan 完成",
        source=[],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="watch_summary", detail=_summary())]),
    )

    validate(response.to_dict())
