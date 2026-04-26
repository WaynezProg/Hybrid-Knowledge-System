from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.schema import validate


@pytest.mark.integration
def test_graphify_preview_returns_schema_valid_detail(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["graphify", "build", "--mode", "preview"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    validate(payload)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["trace"]["route"] == "graph"
    assert payload["trace"]["steps"][0]["kind"] == "graphify_summary"
    assert payload["confidence"] == 1.0
    assert detail["confidence"] == 1.0
    assert set(payload["source"]).issubset({"wiki", "graph"})
    assert payload["source"]
    assert detail["node_count"] > 0


@pytest.mark.integration
def test_graphify_missing_runtime_returns_noinput(cli_runner) -> None:
    result = cli_runner.invoke(app, ["graphify", "build"])

    assert result.exit_code == 66
    payload = json.loads(result.stdout)
    assert payload["trace"]["route"] == "graph"
    assert payload["trace"]["steps"][0]["detail"]["code"] == "NOINPUT"
