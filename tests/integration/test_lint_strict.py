from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest, save_manifest
from hks.core.paths import runtime_paths


def _ingest(cli_runner, working_docs) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0, result.stdout


@pytest.mark.integration
def test_lint_strict_fails_on_error_findings(cli_runner, working_docs, tmp_ks_root) -> None:
    _ingest(cli_runner, working_docs)
    paths = runtime_paths(tmp_ks_root)
    manifest = load_manifest(paths.manifest)
    next(iter(manifest.entries.values())).derived.wiki_pages.append("missing-page")
    save_manifest(manifest, paths.manifest)

    result = cli_runner.invoke(app, ["lint", "--strict"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["kind"] == "lint_summary"
    assert payload["trace"]["steps"][0]["detail"]["severity_counts"]["error"] >= 1


@pytest.mark.integration
def test_lint_strict_threshold_can_fail_on_warning(cli_runner, working_docs, tmp_ks_root) -> None:
    _ingest(cli_runner, working_docs)
    paths = runtime_paths(tmp_ks_root)
    (paths.wiki_pages / "orphan-page.md").write_text(
        "---\n"
        "slug: orphan-page\n"
        "title: Orphan Page\n"
        "summary: Orphan Page\n"
        "source: raw_sources/project-atlas.txt\n"
        "origin: ingest\n"
        "updated_at: 2026-04-26T00:00:00+00:00\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )

    default = cli_runner.invoke(app, ["lint", "--strict"])
    warning = cli_runner.invoke(app, ["lint", "--strict", "--severity-threshold=warning"])

    assert default.exit_code == 0, default.stdout
    assert warning.exit_code == 1
    assert json.loads(warning.stdout)["trace"]["steps"][0]["detail"]["severity_counts"][
        "warning"
    ] >= 1


@pytest.mark.integration
def test_lint_invalid_threshold_returns_usage_json(cli_runner) -> None:
    result = cli_runner.invoke(app, ["lint", "--severity-threshold=garbage"])

    assert result.exit_code == 2
    assert result.stderr.splitlines()[0].startswith("[ks:lint] usage:")
    assert json.loads(result.stdout)["trace"]["steps"][0]["detail"]["exit_code"] == 2
