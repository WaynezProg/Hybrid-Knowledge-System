from __future__ import annotations

import jsonschema
import pytest

from hks.adapters.contracts import (
    load_wiki_artifact_schema,
    load_wiki_candidate_schema,
    load_wiki_summary_schema,
    validate_wiki_artifact,
    validate_wiki_summary,
)
from hks.core.schema import QueryResponse, Trace, TraceStep, validate


def _candidate() -> dict[str, object]:
    return {
        "candidate_id": "candidate-1",
        "schema_version": 1,
        "target_slug": "project-atlas-synthesis",
        "title": "Project Atlas",
        "summary": "Project Atlas summary",
        "body": "# Project Atlas\n\nBody",
        "source_relpath": "project-atlas.txt",
        "extraction_artifact_id": "extract-1",
        "source_fingerprint": "sha",
        "parser_fingerprint": "txt:v1",
        "prompt_version": "wiki-synthesis-v1",
        "provider_id": "fake",
        "model_id": "fake-wiki-synthesizer-v1",
        "confidence": 0.8,
        "diff_summary": "create pages/project-atlas-synthesis.md",
        "findings": [],
    }


def _summary_detail() -> dict[str, object]:
    return {
        "operation": "wiki_synthesize",
        "mode": "apply",
        "candidate": _candidate(),
        "artifact": {
            "artifact_id": "artifact-1",
            "artifact_path": "/tmp/artifact-1.json",
            "schema_version": 1,
            "status": "valid",
        },
        "apply_result": {
            "operation": "create",
            "target_slug": "project-atlas-synthesis",
            "touched_pages": ["pages/project-atlas-synthesis.md"],
            "log_entry_id": "2026-04-26T00:00:00+00:00",
            "conflicts": [],
            "diff_summary": "create pages/project-atlas-synthesis.md",
            "idempotent_apply": False,
        },
        "confidence": 0.8,
        "findings": [],
    }


@pytest.mark.contract
def test_wiki_synthesis_schemas_are_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(load_wiki_candidate_schema())
    jsonschema.Draft202012Validator.check_schema(load_wiki_summary_schema())
    jsonschema.Draft202012Validator.check_schema(load_wiki_artifact_schema())


@pytest.mark.contract
def test_wiki_synthesis_summary_detail_contract_accepts_expected_payload() -> None:
    validate_wiki_summary(_summary_detail())


@pytest.mark.contract
def test_wiki_synthesis_artifact_contract_accepts_expected_payload() -> None:
    validate_wiki_artifact(
        {
            "artifact_id": "artifact-1",
            "schema_version": 1,
            "idempotency_key": "key",
            "created_at": "2026-04-26T00:00:00+00:00",
            "status": "valid",
            "request": {
                "source_relpath": "project-atlas.txt",
                "extraction_artifact_id": None,
                "mode": "store",
                "target_slug": "project-atlas-synthesis",
                "prompt_version": "wiki-synthesis-v1",
                "provider_id": "fake",
                "model_id": "fake-wiki-synthesizer-v1",
                "force_new_run": False,
                "requested_by": None,
            },
            "candidate": _candidate(),
        }
    )


@pytest.mark.contract
def test_query_response_contract_allows_wiki_synthesis_summary_step() -> None:
    response = QueryResponse(
        answer="wiki synthesis 完成",
        source=[],
        confidence=0.8,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="wiki_synthesis_summary", detail=_summary_detail())],
        ),
    )

    validate(response.to_dict())
