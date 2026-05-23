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
def test_md_parser_extracts_session2memory_frontmatter_and_entry_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "2026-05-22.md"
    path.write_text(
        "---\n"
        "hks_type: session_daily\n"
        "date: 2026-05-22\n"
        "source_domain: session_memory\n"
        "generator: session2memory\n"
        "---\n"
        "# 2026-05-22\n\n"
        "- [decision] Vibe coding 使用 HKS daily source。 "
        "(workspace: vibe-coding, evidence: e000001, source: codex, session: s1, lines: 2-2)\n",
        encoding="utf-8",
    )

    parsed = md_parser.parse(path)

    assert parsed.metadata == {
        "hks_type": "session_daily",
        "date": "2026-05-22",
        "source_domain": "session_memory",
        "generator": "session2memory",
    }
    entry = next(segment for segment in parsed.segments if segment.kind == "list_item")
    assert entry.metadata == {
        "hks_type": "session_daily",
        "source_domain": "session_memory",
        "generator": "session2memory",
        "date": "2026-05-22",
        "workspace_id": "vibe-coding",
        "memory_kind": "decision",
        "tool": "codex",
        "session_id": "s1",
        "evidence_id": "e000001",
    }


@pytest.mark.unit
def test_md_session_segment_parsing_does_not_mutate_input_metadata(tmp_path: Path) -> None:
    metadata = {"date": "2026-05-22"}
    body = (
        "# 2026-05-22\n\n"
        "- [decision] Vibe coding 使用 HKS daily source。 "
        "(workspace: vibe-coding, evidence: e000001, source: codex, session: s1, lines: 2-2)\n"
    )

    segments, document_metadata = md_parser._session_segments(body, metadata, tmp_path / "daily.md")

    assert metadata == {"date": "2026-05-22"}
    assert document_metadata["hks_type"] == "session_daily"
    assert segments[1].metadata["workspace_id"] == "vibe-coding"


@pytest.mark.unit
def test_pdf_parser_extracts_text(valid_fixtures: Path) -> None:
    parsed = pdf_parser.parse(valid_fixtures / "clause-3-2.pdf")

    assert "Clause 3.2 text" in parsed.body


@pytest.mark.unit
def test_pdf_parser_raises_for_broken_pdf(fixtures_root: Path) -> None:
    with pytest.raises(KSError) as exc_info:
        pdf_parser.parse(fixtures_root / "broken" / "broken.pdf")

    assert exc_info.value.code == "PDF_READ_ERROR"
