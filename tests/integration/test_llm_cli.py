from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.schema import validate


@pytest.mark.integration
def test_llm_classify_preview_returns_schema_valid_detail(cli_runner, working_docs) -> None:
    ingest = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert ingest.exit_code == 0

    result = cli_runner.invoke(
        app,
        ["llm", "classify", "project-atlas.txt", "--provider", "fake", "--mode", "preview"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    validate(payload)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["source"] == []
    assert payload["trace"]["route"] == "wiki"
    assert payload["trace"]["steps"][0]["kind"] == "llm_extraction_summary"
    assert detail["artifact"] is None
    assert detail["entity_candidates"]
    assert detail["relation_candidates"]


@pytest.mark.integration
def test_llm_classify_malformed_provider_returns_dataerr(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(
        app,
        ["llm", "classify", "project-atlas.txt", "--provider", "fake-malformed"],
    )

    assert result.exit_code == 65
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["code"] == "LLM_OUTPUT_INVALID"


@pytest.mark.integration
def test_llm_classify_missing_source_returns_noinput(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["llm", "classify", "missing.md"])

    assert result.exit_code == 66
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["code"] == "NOINPUT"


@pytest.mark.integration
def test_llm_classify_hosted_provider_without_opt_in_is_usage(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(
        app,
        ["llm", "classify", "project-atlas.txt", "--provider", "hosted-example"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["code"] == "USAGE"


@pytest.mark.integration
def test_llm_classify_side_effect_text_is_ignored(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(
        app,
        ["llm", "classify", "project-atlas.txt", "--provider", "fake-side-effect"],
    )

    assert result.exit_code == 0
    detail = json.loads(result.stdout)["trace"]["steps"][0]["detail"]
    assert detail["findings"][0]["code"] == "side_effect_text_ignored"
