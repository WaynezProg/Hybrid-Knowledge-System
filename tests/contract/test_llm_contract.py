from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_llm_artifact_schema,
    load_llm_summary_schema,
    validate_llm_artifact,
    validate_llm_summary,
)
from hks.core.schema import QueryResponse, Trace, TraceStep, validate


def _summary_detail() -> dict[str, object]:
    evidence = {
        "source_relpath": "project-atlas.txt",
        "chunk_id": None,
        "quote": "Project Atlas",
        "start_offset": 0,
        "end_offset": 13,
    }
    return {
        "operation": "llm_classify",
        "mode": "store",
        "source": {
            "source_relpath": "project-atlas.txt",
            "source_fingerprint": "sha",
            "parser_fingerprint": "txt:v1",
        },
        "provider": {
            "provider_id": "fake",
            "model_id": "fake-llm-extractor-v1",
            "prompt_version": "llm-extraction-v1",
            "generated_at": "2026-04-26T00:00:00+00:00",
        },
        "classification": [{"label": "project", "confidence": 0.8, "evidence": [evidence]}],
        "summary_candidate": "Project Atlas",
        "key_facts": [{"fact": "Project Atlas", "confidence": 0.7, "evidence": [evidence]}],
        "entity_candidates": [
            {
                "candidate_id": "e1",
                "type": "Document",
                "label": "project-atlas.txt",
                "aliases": [],
                "confidence": 0.9,
                "evidence": [evidence],
            },
            {
                "candidate_id": "e2",
                "type": "Concept",
                "label": "Project Atlas",
                "aliases": [],
                "confidence": 0.8,
                "evidence": [evidence],
            },
        ],
        "relation_candidates": [
            {
                "candidate_id": "r1",
                "type": "references",
                "source_candidate_id": "e1",
                "target_candidate_id": "e2",
                "confidence": 0.7,
                "evidence": [evidence],
            }
        ],
        "confidence": 0.8,
        "artifact": {
            "artifact_id": "artifact-1",
            "artifact_path": "/tmp/artifact-1.json",
            "schema_version": 1,
            "status": "valid",
            "idempotent_reuse": True,
        },
        "findings": [],
    }


@pytest.mark.contract
def test_llm_schemas_are_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(load_llm_summary_schema())
    jsonschema.Draft202012Validator.check_schema(load_llm_artifact_schema())


@pytest.mark.contract
def test_llm_summary_detail_contract_accepts_expected_payload() -> None:
    validate_llm_summary(_summary_detail())


@pytest.mark.contract
def test_llm_artifact_contract_accepts_expected_payload() -> None:
    detail = _summary_detail()
    validate_llm_artifact(
        {
            "artifact_id": "artifact-1",
            "schema_version": 1,
            "idempotency_key": "key",
            "created_at": "2026-04-26T00:00:00+00:00",
            "status": "valid",
            "request": {
                "source_relpath": "project-atlas.txt",
                "mode": "store",
                "prompt_version": "llm-extraction-v1",
                "provider_id": "fake",
                "model_id": "fake-llm-extractor-v1",
                "force_new_run": False,
                "requested_by": None,
            },
            "result": detail,
        }
    )


@pytest.mark.contract
def test_query_response_contract_allows_llm_extraction_summary_step() -> None:
    response = QueryResponse(
        answer="llm extraction 完成",
        source=[],
        confidence=0.8,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="llm_extraction_summary", detail=_summary_detail())],
        ),
    )

    validate(response.to_dict())
