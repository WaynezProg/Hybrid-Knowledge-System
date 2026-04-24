"""Phase 2 Foundational: verify ingest stdout shape is backward-compatible.

Phase 1 txt/md/pdf ingest must continue to produce a top-level QueryResponse
and a `trace.steps[kind=ingest_summary].detail` that satisfies the new
contract schema. No Office-specific markers (skipped_segments / pptx_notes)
should appear for Phase 1 formats.
"""

from __future__ import annotations

import json

import pytest

from hks.cli import app


@pytest.mark.integration
@pytest.mark.us1
def test_phase1_fixtures_still_produce_valid_detail(cli_runner, working_docs, tmp_ks_root) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    assert payload["source"] == []
    assert payload["confidence"] == 0.0
    assert payload["trace"]["route"] == "wiki"
    step = payload["trace"]["steps"][0]
    assert step["kind"] == "ingest_summary"

    detail = step["detail"]
    assert "files" in detail, "Phase 2: files[] must be present"
    assert isinstance(detail["files"], list)
    assert len(detail["files"]) > 0

    for file_report in detail["files"]:
        assert set(file_report.keys()) == {
            "path",
            "status",
            "reason",
            "skipped_segments",
            "pptx_notes",
        }
        assert file_report["status"] in {
            "created",
            "updated",
            "skipped",
            "failed",
            "unsupported",
        }
        # Phase 1 formats never carry Office markers.
        assert file_report["skipped_segments"] == []
        assert file_report["pptx_notes"] is None

    # Every created file should be manifested with a parser_fingerprint.
    manifest_path = tmp_ks_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["entries"].values():
        assert "parser_fingerprint" in entry
