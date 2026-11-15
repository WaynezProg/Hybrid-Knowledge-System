from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.adapters import core
from hks.cli import app
from hks.core.schema import validate


@pytest.fixture()
def topic_daily(cli_runner, tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for day, entries in {
        "2026-11-13": ["session2memory 舊日期結果", "只有別天的主題 older-only"],
        "2026-11-14": [
            "session2memory 修復 OpenCode 匯入",
            "Paperclip 任務等待功能",
            "Mogumogu 購物車",
            "修正索引一致性",
            "session2memory2 不同專案",
        ],
        "2026-11-15": ["session2memory 補上回歸測試", "Paperclip 修改排程"],
    }.items():
        lines = [
            "---",
            "hks_type: session_daily",
            f"date: {day}",
            "generator: session2memory",
            "source_domain: coding_session",
            "---",
            f"# {day}",
            "",
            "## Entries",
        ]
        for n, entry in enumerate(entries):
            lines.append(
                f"- [completed] {entry} "
                f"{{workspace_id=agent-code-123 memory_kind=completed tool=codex "
                f"session_id=s{n} evidence_id=e{n} lines=1-1}}"
            )
        (docs / f"{day}.md").write_text("\n".join(lines) + "\n")
    result = cli_runner.invoke(app, ["ingest", str(docs)])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "question,expected",
    [
        ("2026-11-14 session2memory 做了哪些修改？", "修復 OpenCode 匯入"),
        ("What changed in session2memory on 2026-11-14?", "修復 OpenCode 匯入"),
        ("2026-11-14 索引做了哪些修改？", "索引一致性"),
    ],
)
def test_date_and_topic_filters_answer_and_evidence(topic_daily, question, expected) -> None:
    payload = core.hks_query(question=question, writeback="no")
    validate(payload)
    assert expected in payload["answer"]
    assert payload["evidence"]
    for text in [payload["answer"], *(e["quote"] for e in payload["evidence"])]:
        assert "Paperclip" not in text
        assert "Mogumogu" not in text
        assert "舊日期" not in text
        assert "不同專案" not in text
    assert {e["source_relpath"] for e in payload["evidence"]} == {"2026-11-14.md"}


@pytest.mark.parametrize("topic", ["AbsentProject", "older-only"])
def test_missing_date_topic_does_not_fall_back_to_other_content(topic_daily, topic) -> None:
    payload = core.hks_query(question=f"2026-11-14 {topic} 做了哪些修改？", writeback="no")
    assert payload["source"] == []
    assert payload.get("evidence", []) == []
    assert payload["confidence"] == 0


def test_date_range_filters_topic_on_every_day(topic_daily) -> None:
    payload = core.hks_query(
        question="2026-11-14 到 2026-11-15 session2memory 做了哪些修改？", writeback="no"
    )
    assert "修復 OpenCode 匯入" in payload["answer"]
    assert "補上回歸測試" in payload["answer"]
    assert "Paperclip" not in payload["answer"]
    assert "Mogumogu" not in payload["answer"]
    assert {e["source_relpath"] for e in payload["evidence"]} == {"2026-11-14.md", "2026-11-15.md"}


def test_date_only_still_returns_daily_overview(topic_daily, cli_runner) -> None:
    result = cli_runner.invoke(app, ["query", "2026-11-14 做了什麼？", "--writeback=no"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert all(t in payload["answer"] for t in ["session2memory", "Paperclip", "Mogumogu"])


def test_dated_query_in_ordinary_document_library_is_not_session_scoped(cli_runner, tmp_path):
    source = tmp_path / "release.md"
    source.write_text("# Atlas release\n\nAtlas release on 2026-11-14 fixed ERR-4012.\n")
    assert cli_runner.invoke(app, ["ingest", str(source)]).exit_code == 0
    payload = core.hks_query(question="2026-11-14 Atlas ERR-4012", writeback="no")
    assert payload["source"]
    assert "ERR-4012" in payload["answer"]


@pytest.mark.parametrize(
    "question",
    [
        "2026-11-14 的工作摘要",
        "2026-11-14 有哪些決定",
        "2026-11-14 主要成果是什麼",
        "2026-11-14 學到了什麼",
        "2026-11-14 完成了哪些工作",
    ],
)
def test_dated_question_worded_without_a_subject_returns_the_day(topic_daily, question) -> None:
    # What is left of such a question after the date ("工作", "有哪些決定") is wording,
    # not a subject: no entry holds it, so it must not turn the day into a no-hit.
    payload = core.hks_query(question=question, writeback="no")
    validate(payload)
    assert all(t in payload["answer"] for t in ["session2memory", "Paperclip", "Mogumogu"])
    assert {e["source_relpath"] for e in payload["evidence"]} == {"2026-11-14.md"}


@pytest.mark.parametrize(
    "question",
    ["11/13-11/15 之間完成了哪些工作", "2026-11-13 到 2026-11-15 有什麼重點"],
)
def test_date_range_worded_without_a_subject_returns_every_day(topic_daily, question) -> None:
    payload = core.hks_query(question=question, writeback="no")
    validate(payload)
    assert "修復 OpenCode 匯入" in payload["answer"] and "補上回歸測試" in payload["answer"]
    assert "舊日期結果" in payload["answer"]


def test_a_named_subject_stays_a_constraint_whatever_words_surround_it(topic_daily) -> None:
    present = core.hks_query(question="2026-11-14 Paperclip 新增了哪些東西", writeback="no")
    assert "任務等待功能" in present["answer"] and "Mogumogu" not in present["answer"]
    absent = core.hks_query(question="2026-11-14 AbsentProject 新增了哪些東西", writeback="no")
    assert absent["source"] == [] and absent["confidence"] == 0
