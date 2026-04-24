from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.schema import validate


@pytest.mark.contract
@pytest.mark.us4
def test_lint_stub_returns_schema_valid_json(cli_runner) -> None:
    result = cli_runner.invoke(app, ["lint"])

    assert result.exit_code == 0

    payload = json.loads(result.stdout)
    validate(payload)
    assert payload == {
        "answer": "lint 尚未實作，預計於 Phase 3 提供",
        "source": [],
        "confidence": 0.0,
        "trace": {"route": "wiki", "steps": []},
    }


@pytest.mark.contract
@pytest.mark.us4
def test_help_lists_all_phase1_commands(cli_runner) -> None:
    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ingest" in result.stdout
    assert "query" in result.stdout
    assert "lint" in result.stdout
