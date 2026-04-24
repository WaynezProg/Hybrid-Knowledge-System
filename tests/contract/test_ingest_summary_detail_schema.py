"""Contract tests for `contracts/ingest-summary-detail.schema.json` (FR-045)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "specs/002-phase2-ingest-office/contracts/ingest-summary-detail.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict[str, object]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def validator(schema: dict[str, object]) -> Draft202012Validator:
    return Draft202012Validator(schema)


def _empty_detail() -> dict[str, object]:
    return {
        "created": [],
        "updated": [],
        "skipped": [],
        "failures": [],
        "pruned": [],
        "files": [],
    }


@pytest.mark.contract
def test_schema_self_validates(schema: dict[str, object]) -> None:
    Draft202012Validator.check_schema(schema)


@pytest.mark.contract
def test_examples_pass_validation(validator: Draft202012Validator) -> None:
    for example in schema_examples():
        validator.validate(example)


def schema_examples() -> list[dict[str, object]]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return list(payload.get("examples", []))


@pytest.mark.contract
def test_empty_batch_is_valid(validator: Draft202012Validator) -> None:
    validator.validate(_empty_detail())


@pytest.mark.contract
def test_all_failed_batch_is_valid(validator: Draft202012Validator) -> None:
    detail = _empty_detail()
    detail["failures"] = [
        {"path": "raw_sources/a.pptx", "reason": "encrypted"},
        {"path": "raw_sources/b.xlsx", "reason": "corrupt"},
    ]
    detail["files"] = [
        {
            "path": "raw_sources/a.pptx",
            "status": "failed",
            "reason": "encrypted",
            "skipped_segments": [],
            "pptx_notes": None,
        },
        {
            "path": "raw_sources/b.xlsx",
            "status": "failed",
            "reason": "corrupt",
            "skipped_segments": [],
            "pptx_notes": None,
        },
    ]
    validator.validate(detail)


@pytest.mark.contract
def test_invalid_file_status_rejected(validator: Draft202012Validator) -> None:
    detail = _empty_detail()
    detail["files"] = [
        {
            "path": "raw_sources/x.docx",
            "status": "invalid",  # not in enum
            "reason": None,
            "skipped_segments": [],
            "pptx_notes": None,
        }
    ]
    with pytest.raises(ValidationError):
        validator.validate(detail)


@pytest.mark.contract
def test_unknown_skipped_segment_type_rejected(validator: Draft202012Validator) -> None:
    detail = _empty_detail()
    detail["files"] = [
        {
            "path": "raw_sources/x.docx",
            "status": "created",
            "reason": None,
            "skipped_segments": [{"type": "unknown", "count": 1}],
            "pptx_notes": None,
        }
    ]
    with pytest.raises(ValidationError):
        validator.validate(detail)


@pytest.mark.contract
def test_invalid_pptx_notes_rejected(validator: Draft202012Validator) -> None:
    detail = _empty_detail()
    detail["files"] = [
        {
            "path": "raw_sources/x.pptx",
            "status": "created",
            "reason": None,
            "skipped_segments": [],
            "pptx_notes": "maybe",  # not in enum
        }
    ]
    with pytest.raises(ValidationError):
        validator.validate(detail)
