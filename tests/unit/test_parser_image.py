from __future__ import annotations

import pytest

from hks.ingest.parsers import image as image_parser


@pytest.mark.unit
def test_image_parser_extracts_ocr_segments(fixtures_root) -> None:
    parsed = image_parser.parse(fixtures_root / "valid" / "image" / "atlas-dependency.png", "png")

    assert parsed.title == "atlas-dependency"
    assert parsed.segments
    assert all(segment.kind == "ocr_text" for segment in parsed.segments)
    assert any("Atlas" in segment.text for segment in parsed.segments)
    assert all(
        0.0 <= float(segment.metadata["ocr_confidence"]) <= 1.0
        for segment in parsed.segments
    )
    assert all(
        str(segment.metadata["source_engine"]).startswith("tesseract")
        for segment in parsed.segments
    )


@pytest.mark.unit
def test_image_parser_handles_jpeg_alias(fixtures_root) -> None:
    parsed = image_parser.parse(fixtures_root / "valid" / "image" / "mixed-status.jpg", "jpg")

    assert any("Billing Service" in segment.text for segment in parsed.segments)


@pytest.mark.unit
def test_image_parser_marks_ocr_empty_for_graphic_only_fixture(fixtures_root) -> None:
    parsed = image_parser.parse(fixtures_root / "valid" / "image" / "no-text.png", "png")

    assert parsed.segments == []
    assert [
        (segment.type, segment.count) for segment in parsed.skipped_segments
    ] == [("ocr_empty", 1)]
