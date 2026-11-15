from __future__ import annotations

import json

import pytest

from hks.adapters import core
from hks.cli import app
from hks.core.schema import validate


@pytest.fixture()
def chinese_daily(cli_runner, tmp_path, monkeypatch):
    source = tmp_path / "daily.md"
    source.write_text(
        "---\nhks_type: session_daily\ndate: 2026-11-14\ngenerator: session2memory\n---\n"
        "# 2026-11-14\n\n## Entries\n"
        "- [completed] 搬移 s2m 與 HKS {workspace_id=agent-code-123}\n"
        "- [completed] 驗證 session2memory 與 HKS 功能 {workspace_id=agent-code-123}\n"
        "- [completed] Paperclip 任務等待功能 {workspace_id=bootstrap-123}\n"
        "- [completed] Mogumogu 購物車快捷鍵相容性 {workspace_id=shop-123}\n"
        "- [completed] session2memory2 其他專案 {workspace_id=agent-code-123}\n"
    )
    assert cli_runner.invoke(app, ["ingest", str(source)]).exit_code == 0
    import os
    from pathlib import Path

    root = Path(os.environ["KS_ROOT"])
    (root / "query_aliases.json").write_text(
        json.dumps({"session2memory": ["s2m", "會話記憶"], "HKS": ["混合知識系統"]})
    )


@pytest.mark.parametrize("topic", ["s2m", "session2memory", "會話記憶"])
def test_date_aliases_recall_all_equivalent_entries_without_other_projects(chinese_daily, topic):
    result = core.hks_query(question=f"2026-11-14 {topic} 做了哪些修改？", writeback="no")
    validate(result)
    assert "搬移 s2m" in result["answer"] and "驗證 session2memory" in result["answer"]
    assert "session2memory2" not in result["answer"]
    assert "Mogumogu" not in result["answer"] and "Paperclip" not in result["answer"]
    assert result["evidence"]
    assert all("Mogumogu" not in e["quote"] for e in result["evidence"])


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("任務等候功能", "Paperclip 任務等待功能"),
        ("購物車熱鍵相容性", "Mogumogu 購物車快捷鍵相容性"),
        ("購物車快捷鍵兼容性", "Mogumogu 購物車快捷鍵相容性"),
        ("session2memory 功能驗證", "驗證 session2memory 與 HKS 功能"),
    ],
)
def test_chinese_synonyms_keep_original_answer_and_evidence(chinese_daily, topic, expected):
    result = core.hks_query(question=f"2026-11-14 {topic}", writeback="no")
    assert result["answer"] == expected
    assert result["evidence"] and expected in result["evidence"][0]["quote"]


@pytest.mark.parametrize("topic", ["量子電腦部署", "session2memory 購物車", "不存在的中文主題"])
def test_unknown_or_conjunctive_chinese_topic_does_not_expand_to_whole_day(chinese_daily, topic):
    result = core.hks_query(question=f"2026-11-14 {topic}", writeback="no")
    assert result["source"] == [] and result.get("evidence", []) == []
    assert result["confidence"] == 0


@pytest.mark.parametrize(
    "question,answer,source",
    [
        ("Atlas 有哪些隱憂？", "匿名化", "risk.md"),
        ("阿特拉斯的風險是什麼？", "匿名化", "risk.md"),
        ("結帳服務目前狀況如何？", "stable", "ops.md"),
        ("通知服務目前狀態如何？", "healthy", "ops.md"),
        ("notification service 目前狀況如何？", "healthy", "ops.md"),
    ],
)
def test_entity_and_question_facet_survive_fusion(cli_runner, tmp_path, question, answer, source):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "risk.md").write_text("# Atlas risk\nAtlas 的風險是測試資料尚未匿名化。\n")
    (docs / "dependency.md").write_text(
        "# Atlas dependency\nAtlas 依賴 Mobile Gateway，Status 正常。\n"
        "checkout service 與 notification service 依賴 pricing API。\n"
    )
    (docs / "ops.md").write_text(
        "# Operations status\ncheckout service latency is stable.\n"
        "notification service had one incident but is now healthy.\n"
    )
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    from hks.core.paths import runtime_paths

    (runtime_paths().root / "query_aliases.json").write_text(
        json.dumps(
            {
                "Atlas": ["阿特拉斯"],
                "checkout service": ["結帳服務"],
                "notification service": ["通知服務"],
            }
        )
    )
    result = core.hks_query(question=question, writeback="no")
    assert answer in result["answer"], json.dumps(result, ensure_ascii=False)
    assert result["evidence"] and {e["source_relpath"] for e in result["evidence"]} == {source}


def test_known_entity_with_missing_aspect_does_not_bypass_evidence_gate(cli_runner, tmp_path):
    source = tmp_path / "status.md"
    source.write_text("# Status\ncheckout service latency is stable.\nAtlas 風險是交期延誤。")
    assert cli_runner.invoke(app, ["ingest", str(source)]).exit_code == 0
    from hks.core.paths import runtime_paths

    (runtime_paths().root / "query_aliases.json").write_text(
        json.dumps({"checkout service": ["結帳服務"]})
    )
    result = core.hks_query(question="結帳服務有哪些隱憂？", writeback="no")
    assert result["source"] == [] and result.get("evidence", []) == []
