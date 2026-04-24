from __future__ import annotations

import pytest

from hks.ingest.fingerprint import ParserFlags
from hks.ingest.parsers import docx as docx_parser


@pytest.mark.unit
def test_docx_plain_preserves_heading_paragraph_and_list_order(fixtures_root) -> None:
    parsed = docx_parser.parse(fixtures_root / "valid" / "docx" / "plain.docx", ParserFlags())

    assert parsed.title == "Atlas Office Summary"
    assert [segment.kind for segment in parsed.segments] == [
        "heading",
        "paragraph",
        "paragraph",
        "list_item",
        "list_item",
    ]
    assert parsed.segments[0].metadata["level"] == 1
    assert parsed.segments[0].text == "## Atlas Office Summary"
    assert parsed.segments[-1].text == "- Confirm rollout checklist with finance."


@pytest.mark.unit
def test_docx_table_rows_render_as_markdown(fixtures_root) -> None:
    parsed = docx_parser.parse(fixtures_root / "valid" / "docx" / "with_table.docx", ParserFlags())

    table_segments = [segment for segment in parsed.segments if segment.kind == "table_row"]
    assert len(table_segments) == 2
    assert table_segments[0].text == (
        "| team | status | owner |\n| --- | --- | --- |\n| search | green | Iris |"
    )
    assert table_segments[1].text.endswith("| billing | yellow | Noah |")


@pytest.mark.unit
def test_docx_image_emits_placeholder_and_skipped_segment(fixtures_root) -> None:
    parsed = docx_parser.parse(fixtures_root / "valid" / "docx" / "with_image.docx", ParserFlags())

    placeholders = [segment for segment in parsed.segments if segment.kind == "placeholder"]
    assert [segment.text for segment in placeholders] == ["[image: Figure 1: sample]"]
    assert [(segment.type, segment.count) for segment in parsed.skipped_segments] == [("image", 1)]
