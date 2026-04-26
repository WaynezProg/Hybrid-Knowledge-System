from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.schema import validate


@pytest.mark.integration
def test_wiki_synthesize_preview_returns_schema_valid_detail(cli_runner, working_docs) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0
    assert (
        cli_runner.invoke(
            app,
            ["llm", "classify", "project-atlas.txt", "--provider", "fake", "--mode", "store"],
        ).exit_code
        == 0
    )

    result = cli_runner.invoke(
        app,
        [
            "wiki",
            "synthesize",
            "--source-relpath",
            "project-atlas.txt",
            "--target-slug",
            "project-atlas-synthesis",
            "--mode",
            "preview",
            "--provider",
            "fake",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    validate(payload)
    detail = payload["trace"]["steps"][0]["detail"]
    assert payload["source"] == []
    assert payload["trace"]["route"] == "wiki"
    assert payload["trace"]["steps"][0]["kind"] == "wiki_synthesis_summary"
    assert detail["candidate"]["target_slug"] == "project-atlas-synthesis"
    assert detail["confidence"] == detail["candidate"]["confidence"]


@pytest.mark.integration
def test_wiki_synthesize_missing_extraction_artifact_returns_noinput(
    cli_runner,
    working_docs,
) -> None:
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(
        app,
        ["wiki", "synthesize", "--source-relpath", "project-atlas.txt"],
    )

    assert result.exit_code == 66
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["code"] == "NOINPUT"


@pytest.mark.integration
def test_wiki_synthesize_uses_newest_non_stale_extraction_artifact(
    cli_runner,
    working_docs,
) -> None:
    source = working_docs / "project-atlas.txt"
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0
    assert (
        cli_runner.invoke(
            app,
            ["llm", "classify", "project-atlas.txt", "--provider", "fake", "--mode", "store"],
        ).exit_code
        == 0
    )

    source.write_text(
        source.read_text(encoding="utf-8") + "\nNew source fact.\n",
        encoding="utf-8",
    )
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0
    assert (
        cli_runner.invoke(
            app,
            ["llm", "classify", "project-atlas.txt", "--provider", "fake", "--mode", "store"],
        ).exit_code
        == 0
    )

    result = cli_runner.invoke(
        app,
        [
            "wiki",
            "synthesize",
            "--source-relpath",
            "project-atlas.txt",
            "--mode",
            "preview",
            "--provider",
            "fake",
        ],
    )

    assert result.exit_code == 0
