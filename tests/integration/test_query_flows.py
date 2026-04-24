from __future__ import annotations

import json

import pytest

import hks.ingest.extractor as extractor
import hks.ingest.normalizer as normalizer
from hks.cli import app
from hks.core.text_models import TextModelBackend
from hks.ingest.parsers import docx as docx_parser
from hks.ingest.parsers import md as md_parser
from hks.ingest.parsers import pdf as pdf_parser
from hks.ingest.parsers import pptx as pptx_parser
from hks.ingest.parsers import txt as txt_parser
from hks.ingest.parsers import xlsx as xlsx_parser


@pytest.fixture()
def ingested_runtime(cli_runner, working_docs):
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0
    return working_docs


@pytest.mark.integration
@pytest.mark.us2
def test_query_summary_uses_wiki(cli_runner, ingested_runtime) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["route"] == "wiki"
    assert payload["source"] == ["wiki"]
    assert payload["confidence"] == 1.0


@pytest.mark.integration
@pytest.mark.us2
def test_query_detail_uses_vector(cli_runner, ingested_runtime) -> None:
    result = cli_runner.invoke(app, ["query", "clause 3.2 text", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["route"] == "vector"
    assert payload["source"] == ["vector"]
    assert 0 < payload["confidence"] <= 1
    assert "clause 3.2" in payload["answer"].lower()


@pytest.mark.integration
@pytest.mark.us2
def test_query_relation_uses_graph(cli_runner, ingested_runtime) -> None:
    result = cli_runner.invoke(app, ["query", "A 專案延遲影響哪些系統", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["route"] == "graph"
    assert payload["source"] == ["graph"]
    assert "checkout service" in payload["answer"]


@pytest.mark.integration
@pytest.mark.us2
def test_query_no_hit_returns_zero(cli_runner, ingested_runtime) -> None:
    result = cli_runner.invoke(app, ["query", "明天吃什麼", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["answer"] == "未能於現有知識中找到答案"
    assert payload["source"] == []
    assert payload["confidence"] == 0.0


@pytest.mark.integration
@pytest.mark.us2
def test_query_uninitialized_returns_noinput(cli_runner) -> None:
    result = cli_runner.invoke(app, ["query", "Atlas"])

    assert result.exit_code == 66


@pytest.mark.integration
@pytest.mark.us2
def test_query_corrupted_runtime_without_manifest_returns_noinput(
    cli_runner,
    ingested_runtime,
    tmp_ks_root,
) -> None:
    manifest_path = tmp_ks_root / "manifest.json"
    assert manifest_path.exists()
    manifest_path.unlink()

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=no"])

    assert result.exit_code == 66
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][0]["kind"] == "error"


@pytest.mark.integration
@pytest.mark.us2
def test_query_does_not_reparse_sources(
    cli_runner, ingested_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("query must not re-run ingestion pipeline")

    monkeypatch.setattr(txt_parser, "parse", fail_if_called)
    monkeypatch.setattr(md_parser, "parse", fail_if_called)
    monkeypatch.setattr(pdf_parser, "parse", fail_if_called)
    monkeypatch.setattr(docx_parser, "parse", fail_if_called)
    monkeypatch.setattr(xlsx_parser, "parse", fail_if_called)
    monkeypatch.setattr(pptx_parser, "parse", fail_if_called)
    monkeypatch.setattr(normalizer, "chunk", fail_if_called)
    monkeypatch.setattr(extractor, "extract", fail_if_called)

    original_embed_query = TextModelBackend.embed_query
    calls = {"embed_query": 0}

    def counting_embed_query(self: TextModelBackend, text: str) -> list[float]:
        calls["embed_query"] += 1
        return original_embed_query(self, text)

    monkeypatch.setattr(TextModelBackend, "embed_query", counting_embed_query)

    result = cli_runner.invoke(app, ["query", "clause 3.2 text", "--writeback=no"])

    assert result.exit_code == 0
    assert calls["embed_query"] == 1
