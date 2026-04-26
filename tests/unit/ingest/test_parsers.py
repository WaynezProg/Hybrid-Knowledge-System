from __future__ import annotations

from pathlib import Path

import pytest

from hks.errors import KSError
from hks.ingest.parsers import md as md_parser
from hks.ingest.parsers import pdf as pdf_parser
from hks.ingest.parsers import txt as txt_parser


@pytest.mark.unit
def test_txt_parser_returns_non_empty_text(valid_fixtures: Path) -> None:
    parsed = txt_parser.parse(valid_fixtures / "project-atlas.txt")

    assert parsed.title
    assert "供應商交期延遲" in parsed.body


@pytest.mark.unit
def test_md_parser_extracts_heading(valid_fixtures: Path) -> None:
    parsed = md_parser.parse(valid_fixtures / "risk-register.md")

    assert parsed.title == "Risk Register"
    assert "Atlas 專案目前有兩個主要風險" in parsed.body


@pytest.mark.unit
def test_md_parser_strips_yaml_frontmatter_before_heading(tmp_path: Path) -> None:
    path = tmp_path / "deck.md"
    path.write_text(
        "---\n"
        "marp: true\n"
        "style: |\n"
        "  section { color: red; }\n"
        "---\n"
        "# 真正標題\n\n"
        "這是正文。\n",
        encoding="utf-8",
    )

    parsed = md_parser.parse(path)

    assert parsed.title == "真正標題"
    assert "marp: true" not in parsed.body
    assert "這是正文" in parsed.body


@pytest.mark.unit
def test_pdf_parser_extracts_text(valid_fixtures: Path) -> None:
    parsed = pdf_parser.parse(valid_fixtures / "clause-3-2.pdf")

    assert "Clause 3.2 text" in parsed.body


@pytest.mark.unit
def test_pdf_parser_raises_for_broken_pdf(fixtures_root: Path) -> None:
    with pytest.raises(KSError) as exc_info:
        pdf_parser.parse(fixtures_root / "broken" / "broken.pdf")

    assert exc_info.value.code == "PDF_READ_ERROR"
