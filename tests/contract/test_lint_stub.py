from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.schema import validate


@pytest.mark.contract
@pytest.mark.us4
def test_lint_uninitialized_returns_schema_valid_error(cli_runner) -> None:
    result = cli_runner.invoke(app, ["lint"])

    assert result.exit_code == 66

    payload = json.loads(result.stdout)
    validate(payload)
    assert payload["source"] == []
    assert payload["trace"]["route"] == "wiki"
    assert payload["trace"]["steps"][0]["kind"] == "error"
    assert payload["trace"]["steps"][0]["detail"]["exit_code"] == 66


@pytest.mark.contract
@pytest.mark.us4
def test_help_lists_all_phase1_commands(cli_runner) -> None:
    result = cli_runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "ingest" in result.stdout
    assert "query" in result.stdout
    assert "lint" in result.stdout
