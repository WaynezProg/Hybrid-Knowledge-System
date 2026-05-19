"""Tests for PDF parser segment extraction via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from hks.errors import KSError
from hks.ingest.models import ParsedDocument
from hks.ingest.parsers import pdf as pdf_parser
from hks.page_tree.build import build_page_tree


class TestPdfSegments:
    def test_parse_returns_parsed_document(self, generated_pdf_fixtures) -> None:
        path = generated_pdf_fixtures.plain_text

        result = pdf_parser.parse(path)

        assert isinstance(result, ParsedDocument)
        assert result.title == "plain-text"
        assert result.format == "pdf"
        assert "Just text." in result.body

    def test_toc_pdf_produces_heading_segments(self, generated_pdf_fixtures) -> None:
        path = generated_pdf_fixtures.with_toc

        result = pdf_parser.parse(path)

        heading_segments = [segment for segment in result.segments if segment.kind == "heading"]
        assert [segment.text for segment in heading_segments] == [
            "Chapter 1: Introduction",
            "Chapter 2: Methods",
        ]
        assert heading_segments[0].metadata == {"level": 1, "page_number": 1}
        assert any(segment.kind == "paragraph" for segment in result.segments)

    def test_no_toc_font_heuristic_produces_heading_and_paragraph_segments(
        self, generated_pdf_fixtures
    ) -> None:
        path = generated_pdf_fixtures.no_toc_headings

        result = pdf_parser.parse(path)

        headings = [segment for segment in result.segments if segment.kind == "heading"]
        paragraphs = [segment for segment in result.segments if segment.kind == "paragraph"]
        assert [segment.text for segment in headings] == ["Big Heading", "Another Heading"]
        assert headings[0].metadata == {"level": 1, "page_number": 1}
        assert len(paragraphs) >= 1

    def test_plain_uniform_pdf_preserves_body_only_behavior(self, generated_pdf_fixtures) -> None:
        path = generated_pdf_fixtures.plain_text

        result = pdf_parser.parse(path)

        assert result.body.strip() != ""
        assert result.segments == []

    def test_malformed_pdf_with_magic_raises_pdf_read_error(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.pdf"
        path.write_bytes(b"%PDF-1.7\n%%EOF\n")

        with pytest.raises(KSError) as exc_info:
            pdf_parser.parse(path)

        assert exc_info.value.code == "PDF_READ_ERROR"

    def test_mild_font_size_variation_does_not_create_heading_segments(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "mild.pdf"
        _create_mild_variation_pdf(path)

        result = pdf_parser.parse(path)

        assert result.body.strip() != ""
        assert [segment for segment in result.segments if segment.kind == "heading"] == []
        assert result.segments == []

    def test_page_tree_uses_pdf_heading_segments(self, generated_pdf_fixtures) -> None:
        path = generated_pdf_fixtures.with_toc
        parsed = pdf_parser.parse(path)

        nodes = build_page_tree(parsed, parsed.body)

        assert [node.title for node in nodes] == ["Chapter 1: Introduction", "Chapter 2: Methods"]
        assert nodes[0].start_offset == parsed.body.index("Chapter 1: Introduction")
        assert nodes[1].start_offset == parsed.body.index("Chapter 2: Methods")

def _create_mild_variation_pdf(path: Path) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "Slightly larger lead sentence.", fontsize=12)
        page.insert_text((72, 120), "Normal body text. " * 20, fontsize=11)
        doc.save(path)
    finally:
        doc.close()
