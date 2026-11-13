"""022：問句中的 identifier 如何認定，以及它在 trace 中的寫法。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hks.cli import app
from hks.core.schema import validate

DOCS = {
    "tickets.md": "# Tickets\n\nTicket VID-236 的畫面用來決定第三段採用 A 版或 B 版。\n",
    "sheet.md": (
        "# Risk sheet\n\n| No | Item | Risk |\n|---|---|---|\n| 10 | Atlas-10 | risk-10 |\n"
    ),
    "atlas.md": "# Atlas\n\nAtlas 專案目前有 10 個主要風險，最大的是供應商交期延遲。\n",
    "pipeline.md": "# Pipeline\n\nreconcile 步驟會找出同一個 project 內互相矛盾或重複的記憶。\n",
}


@pytest.fixture()
def ask(cli_runner, tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    for name, text in DOCS.items():
        (docs / name).write_text(text, encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0

    def run(question: str) -> dict[str, Any]:
        result = cli_runner.invoke(app, ["query", question, "--writeback=no"])
        assert result.exit_code == 0, result.stdout
        return validate(json.loads(result.stdout))

    return run


def _steps(payload: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [step["detail"] for step in payload["trace"]["steps"] if step["kind"] == kind]


def _sources(payload: dict[str, Any]) -> set[str]:
    return {item["source_relpath"] for item in payload.get("evidence", [])}


@pytest.mark.contract
@pytest.mark.parametrize("spelling", ["VID-236", "VID236", "VID_236"])
def test_one_code_in_any_spelling_finds_the_same_content(ask, spelling: str) -> None:
    payload = ask(f"{spelling} 的畫面用來決定什麼")

    assert payload["source"] != []
    assert _sources(payload) == {"tickets.md"}
    assert _steps(payload, "fallback") == []


@pytest.mark.contract
def test_an_unknown_code_is_reported_in_one_spelling(ask) -> None:
    payload = ask("VID999 的畫面用來決定什麼")

    assert payload["source"] == [] and payload["confidence"] == 0.0
    fallback = _steps(payload, "fallback")[-1]
    assert fallback["reason"] == "identifier_not_found"
    assert fallback["identifiers"] == ["vid-999"]


@pytest.mark.contract
def test_a_code_with_a_short_number_is_not_answered_by_its_bare_words(ask) -> None:
    payload = ask("Atlas-10 對應哪一個 risk")

    assert "atlas.md" not in _sources(payload)
    assert _sources(payload) <= {"sheet.md"}
    dropped = [detail["identifier_filtered"] for detail in _steps(payload, "merge")]
    dropped += [detail["candidates_dropped"] for detail in _steps(payload, "fallback")]
    assert sum(dropped) >= 1, "atlas.md mentions Atlas and 10 but not Atlas-10"


@pytest.mark.contract
def test_a_name_with_a_digit_inside_it_is_not_required_of_the_answer(ask) -> None:
    payload = ask("session2memory 的 reconcile 步驟做了哪些事")

    assert _sources(payload) == {"pipeline.md"}
    assert [detail["identifier_filtered"] for detail in _steps(payload, "merge")] == [0]
