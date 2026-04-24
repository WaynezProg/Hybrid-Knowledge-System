from __future__ import annotations

import json
import shutil
import time

import pytest

from hks.cli import app
from hks.ingest.parsers import docx as docx_parser


@pytest.mark.integration
@pytest.mark.us3
def test_office_degradation_paths_do_not_break_batch(
    cli_runner,
    working_office_docs,
    fixtures_root,
    tmp_ks_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_parse = docx_parser.parse

    def slow_timeout_bomb(path, flags):
        if path.name == "timeout_bomb.docx":
            time.sleep(6)
        return original_parse(path, flags)

    monkeypatch.setattr(docx_parser, "parse", slow_timeout_bomb)
    monkeypatch.setenv("HKS_OFFICE_TIMEOUT_SEC", "5")
    monkeypatch.setenv("HKS_OFFICE_MAX_FILE_MB", "1")

    docs = working_office_docs
    shutil.copytree(fixtures_root / "broken" / "office", docs / "broken")

    result = cli_runner.invoke(app, ["ingest", str(docs)])

    assert result.exit_code == 65, result.stdout
    payload = json.loads(result.stdout)
    detail = payload["trace"]["steps"][0]["detail"]
    assert "xlsx/with_formula.xlsx" in detail["created"]
    assert {"path": "broken/encrypted.pptx", "reason": "encrypted"} in detail["failures"]
    assert {"path": "broken/corrupt.xlsx", "reason": "corrupt"} in detail["failures"]
    assert {"path": "broken/timeout_bomb.docx", "reason": "timeout"} in detail["failures"]
    assert {"path": "broken/oversized.xlsx", "reason": "oversized"} in detail["failures"]
    assert {"path": "broken/empty.docx", "reason": "empty_file"} in detail["skipped"]

    file_reports = {item["path"]: item for item in detail["files"]}
    assert file_reports["xlsx/with_formula.xlsx"]["skipped_segments"] == [
        {"type": "chart", "count": 1},
        {"type": "macros", "count": 1},
    ]

    manifest_payload = json.loads((tmp_ks_root / "manifest.json").read_text(encoding="utf-8"))
    manifest_paths = set(manifest_payload["entries"])
    assert "broken/encrypted.pptx" not in manifest_paths
    assert "broken/corrupt.xlsx" not in manifest_paths
    assert "broken/timeout_bomb.docx" not in manifest_paths
    assert "broken/oversized.xlsx" not in manifest_paths

    raw_sources = {
        path.relative_to(tmp_ks_root / "raw_sources").as_posix()
        for path in (tmp_ks_root / "raw_sources").rglob("*")
        if path.is_file()
    }
    assert "broken/encrypted.pptx" not in raw_sources
    assert "broken/corrupt.xlsx" not in raw_sources
    assert "broken/timeout_bomb.docx" not in raw_sources
    assert "broken/oversized.xlsx" not in raw_sources
