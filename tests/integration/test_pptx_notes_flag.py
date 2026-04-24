from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.cli import app
from hks.core.paths import runtime_paths
from hks.storage.vector import VectorStore


def _vector_count(ks_root: Path) -> int:
    return VectorStore(runtime_paths(ks_root)).count()


@pytest.mark.integration
@pytest.mark.us3
def test_pptx_notes_flag_triggers_reingest_and_removes_notes_hits(
    cli_runner, working_office_docs, tmp_ks_root
) -> None:
    include = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert include.exit_code == 0, include.stdout
    before_count = _vector_count(tmp_ks_root)

    query_before = cli_runner.invoke(app, ["query", "detail fallback supplier", "--writeback=no"])
    assert query_before.exit_code == 0
    before_payload = json.loads(query_before.stdout)
    assert "fallback supplier" in before_payload["answer"]

    exclude = cli_runner.invoke(
        app,
        ["ingest", str(working_office_docs), "--pptx-notes", "exclude"],
    )
    assert exclude.exit_code == 0, exclude.stdout
    payload = json.loads(exclude.stdout)
    assert sorted(payload["trace"]["steps"][0]["detail"]["updated"]) == [
        "pptx/plain.pptx",
        "pptx/with_notes.pptx",
        "pptx/with_table_image.pptx",
    ]

    after_count = _vector_count(tmp_ks_root)
    assert after_count < before_count

    log_text = (tmp_ks_root / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "- pptx_notes: excluded" in log_text

    query_after = cli_runner.invoke(app, ["query", "detail fallback supplier", "--writeback=no"])
    assert query_after.exit_code == 0
    after_payload = json.loads(query_after.stdout)
    assert after_payload["answer"] == "未能於現有知識中找到答案"
