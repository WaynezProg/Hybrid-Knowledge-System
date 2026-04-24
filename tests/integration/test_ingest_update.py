from __future__ import annotations

import json

import pytest

from hks.cli import app


@pytest.mark.integration
@pytest.mark.us1
def test_reingest_updates_changed_file(cli_runner, working_docs, tmp_ks_root) -> None:
    first = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert first.exit_code == 0

    target = working_docs / "risk-register.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n追加：法遵審核延後。",
        encoding="utf-8",
    )

    second = cli_runner.invoke(app, ["ingest", str(working_docs)])

    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    assert payload["trace"]["steps"][0]["detail"]["updated"] == ["risk-register.md"]
    log_text = (tmp_ks_root / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "updated" in log_text
