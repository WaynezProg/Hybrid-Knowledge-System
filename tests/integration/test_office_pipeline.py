from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document

from hks.cli import app
from hks.core.manifest import load_manifest


def _find_page_for_source(pages_dir: Path, relpath: str) -> str:
    for page_path in pages_dir.glob("*.md"):
        text = page_path.read_text(encoding="utf-8")
        if f"source: raw_sources/{relpath}" in text:
            return text
    raise AssertionError(f"wiki page for {relpath} not found")


@pytest.mark.integration
@pytest.mark.us1
def test_office_ingest_pipeline_end_to_end(cli_runner, working_office_docs, tmp_ks_root) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_office_docs)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    detail = payload["trace"]["steps"][0]["detail"]
    assert len(detail["created"]) == 9
    assert detail["updated"] == []
    assert detail["failures"] == []

    raw_files = sorted(path for path in (tmp_ks_root / "raw_sources").rglob("*") if path.is_file())
    assert len(raw_files) == 9
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 9

    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert len(manifest.entries) == 9
    assert all(entry.parser_fingerprint != "*" for entry in manifest.entries.values())

    multi_sheet_page = _find_page_for_source(
        tmp_ks_root / "wiki" / "pages",
        "xlsx/multi_sheet.xlsx",
    )
    assert "## Summary" in multi_sheet_page
    assert "## Budget" in multi_sheet_page
    assert "## Risks" in multi_sheet_page

    rerun = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert rerun.exit_code == 0
    rerun_payload = json.loads(rerun.stdout)
    assert len(rerun_payload["trace"]["steps"][0]["detail"]["skipped"]) == 9

    target = working_office_docs / "docx" / "plain.docx"
    document = Document(target)
    document.add_paragraph("Added update paragraph for reingest coverage.")
    document.save(target)

    updated = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert updated.exit_code == 0
    updated_payload = json.loads(updated.stdout)
    assert updated_payload["trace"]["steps"][0]["detail"]["updated"] == ["docx/plain.docx"]


@pytest.mark.integration
@pytest.mark.us1
def test_mixed_phase1_and_office_formats_ingest_together(
    cli_runner, working_all_docs, tmp_ks_root
) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_all_docs)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["trace"]["steps"][0]["detail"]["created"]) == 19
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 19
