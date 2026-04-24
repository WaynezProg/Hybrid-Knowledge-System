from __future__ import annotations

import pytest

from hks.ingest.fingerprint import ParserFlags
from hks.ingest.parsers import xlsx as xlsx_parser


@pytest.mark.unit
def test_xlsx_single_sheet_emits_sheet_header_and_row_segments(fixtures_root) -> None:
    parsed = xlsx_parser.parse(
        fixtures_root / "valid" / "xlsx" / "single_sheet.xlsx",
        ParserFlags(),
    )

    assert parsed.segments[0].kind == "sheet_header"
    assert parsed.segments[0].metadata["sheet_name"] == "Summary"
    first_row = parsed.segments[1]
    assert first_row.kind == "table_row"
    assert first_row.metadata["row_index"] == 2
    assert first_row.text == (
        "| id | project | risk |\n| --- | --- | --- |\n| 1 | Atlas-1 | risk-1 |"
    )


@pytest.mark.unit
def test_xlsx_multi_sheet_preserves_sheet_order(fixtures_root) -> None:
    parsed = xlsx_parser.parse(fixtures_root / "valid" / "xlsx" / "multi_sheet.xlsx", ParserFlags())

    sheet_headers = [
        segment.metadata["sheet_name"]
        for segment in parsed.segments
        if segment.kind == "sheet_header"
    ]
    assert sheet_headers == ["Summary", "Budget", "Risks"]


@pytest.mark.unit
def test_xlsx_formula_rows_use_cached_value_and_formula_only_metadata(fixtures_root) -> None:
    parsed = xlsx_parser.parse(
        fixtures_root / "valid" / "xlsx" / "with_formula.xlsx",
        ParserFlags(),
    )

    formula_rows = [segment for segment in parsed.segments if segment.kind == "table_row"]
    assert formula_rows[0].text.endswith("| 2 | 3 | 5 |")
    assert formula_rows[1].metadata["formula_only"] is True
    assert formula_rows[1].text.endswith("| 5 | 8 | =SUM(A3:B3) |")
    assert [(segment.type, segment.count) for segment in parsed.skipped_segments] == [
        ("chart", 1),
        ("macros", 1),
    ]
