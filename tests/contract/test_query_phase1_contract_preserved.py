from __future__ import annotations

import json

import jsonschema
import pytest

from hks.cli import app
from hks.core.schema import validate


@pytest.mark.contract
def test_confidence_fields_optional_and_valid() -> None:
    old_payload = {
        "answer": "test",
        "source": ["wiki"],
        "confidence": 0.8,
        "trace": {"route": "wiki", "steps": []},
    }
    validate(old_payload)

    new_payload = {
        **old_payload,
        "retrieval_score": 1.2,
        "writeback_eligible": True,
    }
    validate(new_payload)


@pytest.mark.contract
def test_query_response_rejects_calibrated_confidence() -> None:
    payload = {
        "answer": "test",
        "source": ["wiki"],
        "confidence": 0.8,
        "retrieval_score": 0.8,
        "calibrated_confidence": 0.8,
        "writeback_eligible": True,
        "trace": {"route": "wiki", "steps": []},
    }

    with pytest.raises(jsonschema.ValidationError):
        validate(payload)


@pytest.mark.contract
def test_office_queries_validate_against_phase2_contract(
    cli_runner, working_office_docs
) -> None:
    ingest = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert ingest.exit_code == 0, ingest.stdout

    detail_query = cli_runner.invoke(app, ["query", "detail fallback supplier", "--writeback=no"])
    assert detail_query.exit_code == 0, detail_query.stdout
    detail_payload = json.loads(detail_query.stdout)
    validate(detail_payload)
    assert detail_payload["source"] in (["vector"], ["wiki"])
    assert detail_payload["trace"]["route"] in {"vector", "wiki"}
    vector_detail = next(
        step["detail"]
        for step in detail_payload["trace"]["steps"]
        if step["kind"] == "vector_lookup"
    )
    assert vector_detail["slide_index"] == 3
    assert vector_detail["section_type"] == "notes"

    relation_query = cli_runner.invoke(app, ["query", "why vendor lead time", "--writeback=no"])
    assert relation_query.exit_code == 0, relation_query.stdout
    relation_payload = json.loads(relation_query.stdout)
    validate(relation_payload)
    assert relation_payload["trace"]["route"] in {"graph", "vector"}
    assert relation_payload["source"] in (["graph"], ["vector"])
    assert relation_payload["trace"]["route"] != "wiki"
    assert relation_payload["source"] != ["wiki"]
