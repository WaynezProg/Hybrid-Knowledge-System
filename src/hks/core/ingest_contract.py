"""Runtime validator for the ingest_summary trace detail schema.

Spec FR-045: `ks ingest` top-level response remains Phase 1 QueryResponse;
Office-specific data lives inside `trace.steps[kind=ingest_summary].detail`.
This module loads the JSON schema shipped under
`specs/002-phase2-ingest-office/contracts/ingest-summary-detail.schema.json`
and exposes `validate_ingest_detail()` for runtime self-checks.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_RELPATH = "specs/002-phase2-ingest-office/contracts/ingest-summary-detail.schema.json"


def _repo_root() -> Path:
    # src/hks/core/ingest_contract.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    schema_path = _repo_root() / SCHEMA_RELPATH
    with schema_path.open("r", encoding="utf-8") as handle:
        payload: dict[str, Any] = json.load(handle)
    return payload


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def validate_ingest_detail(detail: dict[str, Any]) -> None:
    """Validate an ingest_summary detail object.

    Raises `jsonschema.ValidationError` on failure so callers can either
    propagate (tests) or wrap into KSError (runtime).
    """

    _validator().validate(detail)
