from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from hks.adapters import core
from hks.adapters.mcp_server import create_server
from hks.core.schema import validate


def _tool_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, CallToolResult):
        assert result.structuredContent is not None
        return dict(result.structuredContent)
    assert isinstance(result, list)
    assert len(result) == 1
    return json.loads(result[0].text)


async def _call_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    server = create_server()
    return _tool_payload(await server.call_tool(name, payload))


def _wiki_page_snapshot(ks_root: Path) -> dict[str, bytes]:
    pages_dir = ks_root / "wiki" / "pages"
    return {path.name: path.read_bytes() for path in sorted(pages_dir.glob("*.md"))}


def _queue_files(ks_root: Path) -> list[Path]:
    return sorted((ks_root / "writeback" / "queue").glob("*.json"))


def _writeback_step(payload: dict[str, Any]) -> dict[str, Any]:
    return next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")


@pytest.mark.integration
def test_mcp_query_matches_core_route_and_source(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    core_payload = core.hks_query(question="Project Atlas summary", writeback="no")

    mcp_payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary"},
    )

    validate(mcp_payload)
    assert mcp_payload["trace"]["route"] == core_payload["trace"]["route"]
    assert mcp_payload["source"] == core_payload["source"]
    assert "ok" not in mcp_payload


@pytest.mark.integration
def test_mcp_does_not_require_http_token(working_docs, monkeypatch) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary"},
    )

    validate(payload)
    assert payload["source"]
    assert "Project Atlas" in payload["answer"]
    assert "ok" not in payload


@pytest.mark.integration
def test_mcp_explicit_ks_root_uses_context(working_docs, tmp_path, monkeypatch) -> None:
    ks_root = tmp_path / "mcp-ks"
    wrong_root = tmp_path / "wrong-ks"
    core.hks_ingest(path=str(working_docs), ks_root=str(ks_root))
    monkeypatch.setenv("KS_ROOT", str(wrong_root))

    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary", "ks_root": str(ks_root)},
    )

    validate(payload)
    assert "Project Atlas" in payload["answer"]
    assert {
        evidence["source_relpath"] for evidence in payload["evidence"]
    } >= {"project-atlas.txt"}
    assert not (wrong_root / "manifest.json").exists()
    assert "ok" not in payload


@pytest.mark.integration
def test_mcp_query_writeback_yes_enqueues_without_wiki_page(
    working_docs,
    tmp_ks_root,
) -> None:
    core.hks_ingest(path=str(working_docs))
    before_pages = _wiki_page_snapshot(tmp_ks_root)

    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary", "writeback": "yes"},
    )

    validate(payload)
    writeback_step = _writeback_step(payload)
    assert writeback_step["detail"]["status"] in {
        "enqueued",
        "enqueued-deduped",
        "already-promoted",
    }
    queue_files = _queue_files(tmp_ks_root)
    assert len(queue_files) == 1
    item = json.loads(queue_files[0].read_text(encoding="utf-8"))
    assert item["question"] == "Project Atlas summary"
    assert item["answer"] == payload["answer"]
    assert _wiki_page_snapshot(tmp_ks_root) == before_pages
    assert "ok" not in payload


@pytest.mark.integration
def test_mcp_query_noinput_returns_adapter_error_envelope() -> None:
    payload = anyio.run(_call_tool, "hks_query", {"question": "Project Atlas summary"})

    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOINPUT"
    assert payload["error"]["exit_code"] == 66
    assert payload["response"]["trace"]["steps"][0]["kind"] == "error"


@pytest.mark.integration
def test_mcp_query_invalid_writeback_returns_usage_envelope() -> None:
    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary", "writeback": "later"},
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert payload["error"]["exit_code"] == 2
    assert "writeback" in payload["error"]["message"]


@pytest.mark.integration
def test_mcp_query_default_does_not_write_back_pages(working_docs, tmp_ks_root) -> None:
    core.hks_ingest(path=str(working_docs))
    pages = tmp_ks_root / "wiki" / "pages"
    before = sorted(path.name for path in pages.glob("*.md"))

    payload = anyio.run(_call_tool, "hks_query", {"question": "Project Atlas summary"})

    assert payload["source"] == ["wiki"]
    assert sorted(path.name for path in pages.glob("*.md")) == before
