from __future__ import annotations

import pytest

from hks.ingest.fingerprint import ParserFlags
from hks.ingest.parsers import pptx as pptx_parser


@pytest.mark.unit
def test_pptx_plain_slide_headers_are_deterministic(fixtures_root) -> None:
    parsed = pptx_parser.parse(fixtures_root / "valid" / "pptx" / "plain.pptx", ParserFlags())

    slide_headers = [segment for segment in parsed.segments if segment.kind == "slide_header"]
    assert [segment.metadata["slide_index"] for segment in slide_headers] == [1, 2, 3, 4, 5]


@pytest.mark.unit
def test_pptx_notes_respect_flag(fixtures_root) -> None:
    path = fixtures_root / "valid" / "pptx" / "with_notes.pptx"
    included = pptx_parser.parse(path, ParserFlags(pptx_notes=True))
    excluded = pptx_parser.parse(path, ParserFlags(pptx_notes=False))

    assert [segment.kind for segment in included.segments[:4]] == [
        "slide_header",
        "heading",
        "paragraph",
        "notes",
    ]
    assert [segment.kind for segment in excluded.segments[:3]] == [
        "slide_header",
        "heading",
        "paragraph",
    ]
    assert not any(segment.kind == "notes" for segment in excluded.segments)


@pytest.mark.unit
def test_pptx_table_and_image_only_slides_emit_expected_segments(fixtures_root) -> None:
    parsed = pptx_parser.parse(
        fixtures_root / "valid" / "pptx" / "with_table_image.pptx",
        ParserFlags(),
    )

    placeholders = [segment for segment in parsed.segments if segment.kind == "placeholder"]
    assert [segment.text for segment in placeholders] == [
        "[image: Picture 1]",
        "[image: Picture 3]",
    ]
    slide_headers = [
        segment.metadata["slide_index"]
        for segment in parsed.segments
        if segment.kind == "slide_header"
    ]
    assert slide_headers == [1, 2, 3]
    assert [(segment.type, segment.count) for segment in parsed.skipped_segments] == [("image", 2)]
