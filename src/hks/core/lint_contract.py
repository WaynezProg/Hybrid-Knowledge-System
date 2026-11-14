"""Runtime validator for the lint_summary trace detail schema."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from hks.core.resources import resource_root


def lint_detail_schema_path() -> Path:
    return (
        resource_root()
        / "specs"
        / "005-phase3-lint-impl"
        / "contracts"
        / "lint-summary-detail.schema.json"
    )


@lru_cache(maxsize=1)
def load_lint_detail_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(
        lint_detail_schema_path().read_text(encoding="utf-8")
    )
    return schema


def validate_lint_detail(detail: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(instance=detail, schema=load_lint_detail_schema())
    return detail
