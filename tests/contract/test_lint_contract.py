from __future__ import annotations

import jsonschema
import pytest

from hks.core.lint_contract import load_lint_detail_schema, validate_lint_detail


@pytest.mark.contract
def test_lint_detail_schema_is_valid() -> None:
    jsonschema.Draft202012Validator.check_schema(load_lint_detail_schema())


@pytest.mark.contract
def test_lint_detail_schema_accepts_empty_summary() -> None:
    detail = {
        "findings": [],
        "severity_counts": {"error": 0, "warning": 0, "info": 0},
        "category_counts": {},
        "fixes_planned": [],
        "fixes_applied": [],
        "fixes_skipped": [],
    }

    assert validate_lint_detail(detail) == detail


@pytest.mark.contract
def test_lint_detail_schema_rejects_unknown_category() -> None:
    detail = {
        "findings": [
            {
                "category": "typo_check",
                "severity": "warning",
                "target": "x",
                "message": "x",
            }
        ],
        "severity_counts": {"error": 0, "warning": 1, "info": 0},
        "category_counts": {"typo_check": 1},
        "fixes_planned": [],
        "fixes_applied": [],
        "fixes_skipped": [],
    }

    with pytest.raises(jsonschema.ValidationError):
        validate_lint_detail(detail)
