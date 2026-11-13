"""021：`--writeback=no` 的查詢不寫 wiki/log.md，只在 trace 留 writeback step。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import hks.commands.query as query_command
from hks.cli import app
from hks.core.schema import validate
from hks.writeback.gate import Decision

QUESTION = "summary Atlas"


@pytest.fixture()
def log_path(cli_runner, working_docs, tmp_ks_root: Path) -> Path:
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0, result.stdout
    path = tmp_ks_root / "wiki" / "log.md"
    assert path.is_file()
    return path


def _writeback_step(payload: dict) -> dict:
    last = payload["trace"]["steps"][-1]
    assert last["kind"] == "writeback"
    return last["detail"]


@pytest.mark.contract
@pytest.mark.parametrize("arguments", [["--writeback=no"], []], ids=["explicit-no", "default"])
def test_writeback_no_leaves_the_log_untouched(cli_runner, log_path: Path, arguments) -> None:
    before = log_path.read_bytes()

    result = cli_runner.invoke(app, ["query", QUESTION, *arguments])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    validate(payload)
    assert payload["source"] == ["wiki"]
    assert _writeback_step(payload) == {"status": "declined"}
    assert log_path.read_bytes() == before


@pytest.mark.contract
def test_writeback_no_without_an_answer_leaves_the_log_untouched(
    cli_runner, log_path: Path
) -> None:
    before = log_path.read_bytes()

    result = cli_runner.invoke(app, ["query", "ERR-99999 怎麼修", "--writeback=no"])

    payload = json.loads(result.stdout)
    assert payload["source"] == []
    assert _writeback_step(payload) == {"status": "skip-no-source"}
    assert log_path.read_bytes() == before


@pytest.mark.contract
def test_skipped_auto_writeback_is_still_logged(cli_runner, log_path: Path) -> None:
    before = log_path.read_text(encoding="utf-8")

    result = cli_runner.invoke(app, ["query", QUESTION, "--writeback=auto"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert _writeback_step(payload) == {"status": "auto-skipped-ineligible"}
    added = log_path.read_text(encoding="utf-8")[len(before) :]
    assert "| writeback | auto-skipped-ineligible" in added
    assert f"- query: {QUESTION}" in added


@pytest.mark.contract
def test_declined_ask_is_still_logged(cli_runner, log_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        query_command,
        "decide",
        lambda flag, *, assessment=None, confidence=None, is_tty=False, prompt=None: Decision(
            action="decline", status="declined"
        ),
    )
    before = log_path.read_text(encoding="utf-8")

    result = cli_runner.invoke(app, ["query", QUESTION, "--writeback=ask"])

    assert result.exit_code == 0, result.stdout
    assert _writeback_step(json.loads(result.stdout)) == {"status": "declined"}
    added = log_path.read_text(encoding="utf-8")[len(before) :]
    assert "| writeback | declined" in added
