from __future__ import annotations

import json
from pathlib import Path

import pytest

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
def test_image_ingest_pipeline_end_to_end(cli_runner, working_image_docs, tmp_ks_root) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_image_docs)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    detail = payload["trace"]["steps"][0]["detail"]
    assert len(detail["created"]) == 5
    assert {"path": "no-text.png", "reason": "ocr_empty"} in detail["skipped"]
    assert detail["updated"] == []
    assert detail["failures"] == []

    raw_files = sorted(path for path in (tmp_ks_root / "raw_sources").rglob("*") if path.is_file())
    assert len(raw_files) == 5
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 5

    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert len(manifest.entries) == 5
    assert all(entry.parser_fingerprint != "*" for entry in manifest.entries.values())

    atlas_page = _find_page_for_source(tmp_ks_root / "wiki" / "pages", "atlas-dependency.png")
    assert "Atlas" in atlas_page
    assert "Mobile Gateway" in atlas_page

    rerun = cli_runner.invoke(app, ["ingest", str(working_image_docs)])
    assert rerun.exit_code == 0, rerun.stdout
    rerun_payload = json.loads(rerun.stdout)
    assert len(rerun_payload["trace"]["steps"][0]["detail"]["skipped"]) == 6

    target = working_image_docs / "atlas-dependency.png"
    with target.open("ab") as handle:
        handle.write(b"\nphase3-update")

    updated = cli_runner.invoke(app, ["ingest", str(working_image_docs)])
    assert updated.exit_code == 0, updated.stdout
    updated_payload = json.loads(updated.stdout)
    assert updated_payload["trace"]["steps"][0]["detail"]["updated"] == ["atlas-dependency.png"]


@pytest.mark.integration
@pytest.mark.us1
def test_mixed_phase123_formats_ingest_together(
    cli_runner,
    working_phase3_docs,
    tmp_ks_root,
) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_phase3_docs)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    detail = payload["trace"]["steps"][0]["detail"]
    assert len(detail["created"]) == 24
    assert {"path": "image/no-text.png", "reason": "ocr_empty"} in detail["skipped"]
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 24
