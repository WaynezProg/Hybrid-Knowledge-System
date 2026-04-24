from __future__ import annotations

import json

import pytest

import hks.ingest.extractor as extractor
import hks.ingest.normalizer as normalizer
from hks.cli import app
from hks.core.text_models import TextModelBackend
from hks.ingest.parsers import docx as docx_parser
from hks.ingest.parsers import pptx as pptx_parser
from hks.ingest.parsers import xlsx as xlsx_parser


@pytest.fixture()
def office_runtime(cli_runner, working_office_docs):
    result = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert result.exit_code == 0, result.stdout
    return working_office_docs


@pytest.mark.integration
@pytest.mark.us2
def test_query_office_content_hits_with_phase2_contract(cli_runner, office_runtime) -> None:
    cases = [
        ("summary Atlas Office Summary", "wiki", ["wiki"]),
        ("summary multi sheet", "wiki", ["wiki"]),
        ("detail Q2 135", "vector", ["vector"]),
        ("detail fallback supplier", "vector", ["vector"]),
        ("detail Picture 1", "vector", ["vector"]),
        ("why vendor lead time", None, None),
    ]

    seen_budget = False
    seen_notes = False
    seen_placeholder = False
    seen_relation_trace = False
    for question, expected_route, expected_source in cases:
        result = cli_runner.invoke(app, ["query", question, "--writeback=no"])
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        if expected_route is not None:
            assert payload["trace"]["route"] == expected_route
        if expected_source is not None:
            assert payload["source"] == expected_source
        assert payload["trace"]["route"] in {"wiki", "graph", "vector"}
        assert set(payload["source"]).issubset({"wiki", "graph", "vector"})

        if question == "detail Q2 135":
            vector_detail = next(
                step["detail"]
                for step in payload["trace"]["steps"]
                if step["kind"] == "vector_lookup"
            )
            assert vector_detail["sheet_name"] == "Budget"
            assert vector_detail["section_type"] == "table_row"
            seen_budget = True
        elif question == "detail fallback supplier":
            vector_detail = next(
                step["detail"]
                for step in payload["trace"]["steps"]
                if step["kind"] == "vector_lookup"
            )
            assert vector_detail["slide_index"] == 3
            assert vector_detail["section_type"] == "notes"
            seen_notes = True
        elif question == "detail Picture 1":
            vector_detail = next(
                step["detail"]
                for step in payload["trace"]["steps"]
                if step["kind"] == "vector_lookup"
            )
            assert vector_detail["slide_index"] == 2
            assert vector_detail["section_type"] == "placeholder"
            seen_placeholder = True
        elif question == "why vendor lead time":
            kinds = [step["kind"] for step in payload["trace"]["steps"]]
            assert "graph_lookup" in kinds or "vector_lookup" in kinds
            seen_relation_trace = True

    assert seen_budget and seen_notes and seen_placeholder and seen_relation_trace


@pytest.mark.integration
@pytest.mark.us2
def test_query_office_hits_do_not_reparse_sources(
    cli_runner, office_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("query must not parse Office source files")

    monkeypatch.setattr(docx_parser, "parse", fail_if_called)
    monkeypatch.setattr(xlsx_parser, "parse", fail_if_called)
    monkeypatch.setattr(pptx_parser, "parse", fail_if_called)
    monkeypatch.setattr(normalizer, "segment_aware_chunks", fail_if_called)
    monkeypatch.setattr(extractor, "extract", fail_if_called)

    original_embed_query = TextModelBackend.embed_query
    calls = {"embed_query": 0}

    def counting_embed_query(self: TextModelBackend, text: str) -> list[float]:
        calls["embed_query"] += 1
        return original_embed_query(self, text)

    monkeypatch.setattr(TextModelBackend, "embed_query", counting_embed_query)

    result = cli_runner.invoke(app, ["query", "detail Monday owner", "--writeback=no"])

    assert result.exit_code == 0, result.stdout
    assert calls["embed_query"] == 1
