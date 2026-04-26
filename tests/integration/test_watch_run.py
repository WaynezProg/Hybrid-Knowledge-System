from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest


@pytest.mark.integration
def test_watch_dry_run_does_not_reingest(cli_runner, tmp_path, tmp_ks_root) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    before = load_manifest(tmp_ks_root / "manifest.json").entries["a.md"].sha256
    source.write_text("Alpha owns Atlas v2.\n", encoding="utf-8")

    result = cli_runner.invoke(
        app,
        [
            "watch",
            "run",
            "--source-root",
            str(docs),
            "--mode",
            "dry-run",
            "--profile",
            "ingest-only",
        ],
    )

    assert result.exit_code == 0
    assert load_manifest(tmp_ks_root / "manifest.json").entries["a.md"].sha256 == before
    detail = json.loads(result.stdout)["trace"]["steps"][0]["detail"]
    assert detail["action_counts"]["planned"] == 1


@pytest.mark.integration
def test_watch_execute_ingest_only_reingests_stale_source(
    cli_runner,
    tmp_path,
    tmp_ks_root,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    before = load_manifest(tmp_ks_root / "manifest.json").entries["a.md"].sha256
    source.write_text("Alpha owns Atlas v2.\n", encoding="utf-8")

    result = cli_runner.invoke(
        app,
        [
            "watch",
            "run",
            "--source-root",
            str(docs),
            "--mode",
            "execute",
            "--profile",
            "ingest-only",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["source"] == ["wiki", "graph", "vector"]
    assert load_manifest(tmp_ks_root / "manifest.json").entries["a.md"].sha256 != before
    assert payload["trace"]["steps"][0]["detail"]["action_counts"]["completed"] == 1


@pytest.mark.integration
def test_watch_execute_graphify_profile_writes_graphify_artifacts(
    cli_runner,
    tmp_path,
    tmp_ks_root,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "a.md"
    source.write_text("Alpha owns Atlas.\n", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    source.write_text("Alpha owns Atlas v2.\n", encoding="utf-8")

    result = cli_runner.invoke(
        app,
        [
            "watch",
            "run",
            "--source-root",
            str(docs),
            "--mode",
            "execute",
            "--profile",
            "derived-refresh",
            "--include-graphify",
        ],
    )

    assert result.exit_code == 0
    assert (tmp_ks_root / "graphify" / "latest.json").exists()
