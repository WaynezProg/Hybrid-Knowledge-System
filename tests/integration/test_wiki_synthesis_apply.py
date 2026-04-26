from __future__ import annotations

import json

import pytest

from hks.cli import app


def _stored_candidate_id(cli_runner, working_docs, *, target_slug: str) -> str:
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
            target_slug,
            "--mode",
            "store",
        ],
    )
    assert result.exit_code == 0
    return str(json.loads(result.stdout)["trace"]["steps"][0]["detail"]["artifact"]["artifact_id"])


@pytest.mark.integration
def test_wiki_synthesis_apply_writes_llm_wiki_page_and_is_idempotent(
    cli_runner,
    working_docs,
    tmp_ks_root,
) -> None:
    artifact_id = _stored_candidate_id(
        cli_runner,
        working_docs,
        target_slug="project-atlas-synthesis",
    )

    first = cli_runner.invoke(
        app,
        ["wiki", "synthesize", "--candidate-artifact-id", artifact_id, "--mode", "apply"],
    )
    second = cli_runner.invoke(
        app,
        ["wiki", "synthesize", "--candidate-artifact-id", artifact_id, "--mode", "apply"],
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["source"] == ["wiki"]
    apply_result = second_payload["trace"]["steps"][0]["detail"]["apply_result"]
    assert apply_result["operation"] == "already_applied"
    page = (tmp_ks_root / "wiki" / "pages" / "project-atlas-synthesis.md").read_text(
        encoding="utf-8"
    )
    assert "origin: llm_wiki" in page
    assert f"wiki_candidate_artifact_id: {artifact_id}" in page
    assert not (tmp_ks_root / "graph" / "graph.json").read_text(encoding="utf-8") == ""


@pytest.mark.integration
def test_wiki_synthesis_apply_conflicts_with_ingest_page(cli_runner, working_docs) -> None:
    artifact_id = _stored_candidate_id(cli_runner, working_docs, target_slug="project-atlas")

    result = cli_runner.invoke(
        app,
        ["wiki", "synthesize", "--candidate-artifact-id", artifact_id, "--mode", "apply"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["source"] == []
    assert payload["trace"]["steps"][0]["detail"]["apply_result"]["operation"] == "conflict"
