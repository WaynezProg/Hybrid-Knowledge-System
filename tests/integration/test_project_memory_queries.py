"""Generated project memory must answer as one source-bound record, not a token slice."""

from __future__ import annotations

import json

import pytest

from hks.adapters import core
from hks.cli import app
from hks.core.schema import validate

RULES = [
    ("m_123456abcd", "pytest、ruff、mypy 與 PR CI 都要驗收；Mac 改動另跑 swift test。"),
    (
        "m_234567bcde",
        "OpenCode adapter 同時讀新舊資料表：新表有訊息就用 session_v2 與 session_message，"
        "否則回退舊表，同一對話只計一次。",
    ),
    ("m_345678cdef", "hook 的目標路徑未變時沿用既有核准，逐 agent 驗收 SessionStart 注入。"),
    (
        "m_456789def0",
        "vector evidence gate 只在 similarity 與 coverage 都可量測時判斷；"
        "不可把未量測 coverage 當 0 拒答。",
    ),
]


def project_document(project: str = "/work/session2memory") -> str:
    lines = [
        "---",
        "type: project_memory",
        f"project: {project}",
        f"memories: {len(RULES)}",
        "---",
        "",
        f"# 專案記憶：{project}",
        "",
        "## 做法",
        "",
    ]
    # Each id follows the full stop in its rule. The old passage splitter detached it
    # from its body and paired it with text from the following rule.
    for mid, text in RULES:
        lines.append(f"- {text}（{mid}；確認於 2026-11-16；來源 claude:original、codex:review）")
    return "\n".join(lines) + "\n"


@pytest.fixture()
def memory_corpus(cli_runner, tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "current.md").write_text(project_document())
    (docs / "history.md").write_text(
        "# s2m 補上 OpenCode 支援\n\n確認 s2m 能讀 OpenCode 的 session（opencode.db）。\n"
        "這是歷史支援驗收背景。\n"
    )
    (docs / "fixture.md").write_text(
        "# s2m acceptance\n部署前一律先跑 make check，沒過就不部署。\n"
    )
    assert cli_runner.invoke(app, ["ingest", str(docs)]).exit_code == 0
    from hks.core.paths import runtime_paths

    (runtime_paths().root / "query_aliases.json").write_text(
        json.dumps({"session2memory": ["s2m"]})
    )


@pytest.mark.parametrize("mid,text", RULES)
@pytest.mark.parametrize("mode", ["route", "fused", "off"])
def test_memory_identifier_returns_its_whole_rule_and_only_its_own_evidence(
    memory_corpus, monkeypatch, mid, text, mode
):
    monkeypatch.setenv("HKS_HYBRID_SEARCH", mode)
    result = core.hks_query(question=f"{mid} 這條 s2m 記憶的規則是什麼？", writeback="no")
    validate(result)
    assert text in result["answer"]
    assert {item["source_relpath"] for item in result["evidence"]} == {"current.md"}
    assert result["evidence"][0]["quote"] == text
    for other_id, other_text in RULES:
        if other_id != mid:
            assert other_text not in result["answer"]
    assert result.get("writeback_eligible") is False


@pytest.mark.parametrize("topic", ["s2m", "session2memory"])
@pytest.mark.parametrize("mode", ["route", "fused", "off"])
def test_opencode_schema_question_returns_the_current_rule_not_a_history_title(
    memory_corpus, monkeypatch, topic, mode
):
    monkeypatch.setenv("HKS_HYBRID_SEARCH", mode)
    result = core.hks_query(
        question=f"{topic} 的 OpenCode adapter 如何讀取新舊資料表？", writeback="no"
    )
    assert RULES[1][1] in result["answer"]
    assert result["evidence"][0]["quote"] == RULES[1][1]
    assert all(item["source_relpath"] == "current.md" for item in result["evidence"])


def test_unknown_memory_id_is_not_answered_by_another_record(memory_corpus):
    result = core.hks_query(question="m_999999ffff s2m 的 OpenCode 規則", writeback="no")
    assert result["source"] == [] and result["confidence"] == 0


def test_a_project_name_alone_does_not_claim_every_rule_as_an_answer(memory_corpus):
    result = core.hks_query(question="s2m 火星殖民計畫", writeback="no")
    assert RULES[1][1] not in result["answer"]


def test_query_does_not_change_source_or_derived_artifacts(memory_corpus):
    import hashlib

    from hks.core.paths import runtime_paths

    root = runtime_paths().root

    def files():
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in (root / "raw_sources", root / "wiki", root / "graph", root / "page_trees")
            for path in folder.rglob("*")
            if path.is_file()
        } | {"manifest": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()}

    before = files()
    core.hks_query(question="m_234567bcde s2m 規則", writeback="no")
    assert files() == before
