from __future__ import annotations

import json
import shutil

import pytest

from hks.cli import app


@pytest.mark.integration
@pytest.mark.us1
def test_ingest_handles_broken_pdf_and_continues(cli_runner, working_docs, fixtures_root) -> None:
    shutil.copy(fixtures_root / "broken" / "broken.pdf", working_docs / "broken.pdf")

    result = cli_runner.invoke(app, ["ingest", str(working_docs)])

    assert result.exit_code == 65
    payload = json.loads(result.stdout)
    failures = payload["trace"]["steps"][0]["detail"]["failures"]
    assert failures == [{"path": "broken.pdf", "reason": "pdf_read_error"}]
    assert len(list((working_docs.parent / "ks" / "wiki" / "pages").glob("*.md"))) == 10


@pytest.mark.integration
@pytest.mark.us1
def test_ingest_marks_unsupported_and_empty_as_skipped(cli_runner, tmp_path, fixtures_root) -> None:
    docs = tmp_path / "docs"
    shutil.copytree(fixtures_root / "skip", docs)

    result = cli_runner.invoke(app, ["ingest", str(docs)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    skipped = payload["trace"]["steps"][0]["detail"]["skipped"]
    assert {"path": "unsupported.csv", "reason": "unsupported"} in skipped
    assert {"path": "empty.txt", "reason": "empty"} in skipped
    assert {"path": "whitespace.md", "reason": "empty"} in skipped


@pytest.mark.integration
@pytest.mark.us1
def test_ingest_rejects_oversized_file(
    cli_runner,
    tmp_path,
    fixtures_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = tmp_path / "docs"
    shutil.copytree(fixtures_root / "oversized", docs)
    monkeypatch.setenv("HKS_MAX_FILE_MB", "1")

    result = cli_runner.invoke(app, ["ingest", str(docs)])

    assert result.exit_code == 65
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["detail"]["failures"] == [
        {"path": "big.txt", "reason": "oversized"}
    ]
