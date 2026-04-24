from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.core.manifest import load_manifest


@pytest.mark.integration
@pytest.mark.us1
def test_ingest_builds_runtime_artifacts(cli_runner, working_docs, tmp_ks_root) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["created"]
    assert len(list((tmp_ks_root / "raw_sources").rglob("*.*"))) == 10
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10

    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert len(manifest.entries) == 10
    assert all(entry.sha256 for entry in manifest.entries.values())


@pytest.mark.integration
@pytest.mark.us1
def test_reingest_skips_unchanged_files(cli_runner, working_docs, tmp_ks_root) -> None:
    first = cli_runner.invoke(app, ["ingest", str(working_docs)])
    second = cli_runner.invoke(app, ["ingest", str(working_docs)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    assert len(payload["trace"]["steps"][0]["detail"]["skipped"]) == 10
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10
