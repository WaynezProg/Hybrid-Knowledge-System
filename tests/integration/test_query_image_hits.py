from __future__ import annotations

import json

import pytest

import hks.ingest.extractor as extractor
import hks.ingest.normalizer as normalizer
from hks.cli import app
from hks.core.text_models import TextModelBackend
from hks.ingest.parsers import image as image_parser


@pytest.fixture()
def image_runtime(cli_runner, working_image_docs):
    result = cli_runner.invoke(app, ["ingest", str(working_image_docs)])
    assert result.exit_code == 0, result.stdout
    return working_image_docs


@pytest.mark.integration
@pytest.mark.us2
def test_query_image_content_hits_with_existing_contract(cli_runner, image_runtime) -> None:
    cases = [
        ("summary atlas dependency", "wiki", ["wiki"]),
        ("detail Owner Iris", "vector", ["vector"]),
        ("Atlas 依賴什麼", "graph", ["graph"]),
        ("detail Owner Mia", "vector", ["vector"]),
    ]

    seen_png_detail = False
    seen_jpeg_detail = False
    for question, expected_route, expected_source in cases:
        result = cli_runner.invoke(app, ["query", question, "--writeback=no"])
        assert result.exit_code == 0, result.stdout
        payload = json.loads(result.stdout)
        assert payload["trace"]["route"] == expected_route
        assert payload["source"] == expected_source

        if question == "detail Owner Iris":
            vector_detail = next(
                step["detail"]
                for step in payload["trace"]["steps"]
                if step["kind"] == "vector_lookup"
            )
            assert vector_detail["source_format"] == "png"
            assert float(vector_detail["ocr_confidence"]) > 0.5
            assert vector_detail["source_engine"].startswith("tesseract")
            seen_png_detail = True
        elif question == "detail Owner Mia":
            vector_detail = next(
                step["detail"]
                for step in payload["trace"]["steps"]
                if step["kind"] == "vector_lookup"
            )
            assert vector_detail["source_format"] in {"jpg", "jpeg"}
            assert float(vector_detail["ocr_confidence"]) > 0.5
            seen_jpeg_detail = True
        elif question == "Atlas 依賴什麼":
            assert "Mobile Gateway" in payload["answer"]

    assert seen_png_detail and seen_jpeg_detail


@pytest.mark.integration
@pytest.mark.us2
def test_query_image_hits_do_not_reparse_sources(
    cli_runner, image_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("query must not parse image sources")

    monkeypatch.setattr(image_parser, "parse", fail_if_called)
    monkeypatch.setattr(normalizer, "segment_aware_chunks", fail_if_called)
    monkeypatch.setattr(extractor, "extract", fail_if_called)
    monkeypatch.setattr("hks.ingest.ocr.run_ocr", fail_if_called)

    original_embed_query = TextModelBackend.embed_query
    calls = {"embed_query": 0}

    def counting_embed_query(self: TextModelBackend, text: str) -> list[float]:
        calls["embed_query"] += 1
        return original_embed_query(self, text)

    monkeypatch.setattr(TextModelBackend, "embed_query", counting_embed_query)

    result = cli_runner.invoke(app, ["query", "detail Owner Iris", "--writeback=no"])

    assert result.exit_code == 0, result.stdout
    assert calls["embed_query"] == 1
