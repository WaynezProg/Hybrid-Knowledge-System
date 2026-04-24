from __future__ import annotations

import re

import pytest

from hks.ingest.fingerprint import ParserFlags
from hks.ingest.office_common import build_placeholder
from hks.ingest.parsers import docx as docx_parser
from hks.ingest.parsers import pptx as pptx_parser
from hks.ingest.parsers import xlsx as xlsx_parser

PLACEHOLDER_RE = re.compile(
    r"\[(image|embedded object|smartart|macros|video|audio|chart|pivot): [^\]]*\]"
)


@pytest.mark.contract
def test_placeholder_literals_match_contract_regex() -> None:
    placeholders = [
        build_placeholder("image", "Figure 1"),
        build_placeholder("embedded_object", "Excel.Sheet.12"),
        build_placeholder("smartart", ""),
        build_placeholder("macros"),
        build_placeholder("video"),
        build_placeholder("audio"),
        build_placeholder("chart"),
        build_placeholder("pivot"),
    ]
    assert all(PLACEHOLDER_RE.fullmatch(value) for value in placeholders)


@pytest.mark.contract
def test_parser_outputs_round_trip_placeholder_literals(fixtures_root) -> None:
    placeholders = []
    placeholders.extend(
        segment.text
        for segment in docx_parser.parse(
            fixtures_root / "valid" / "docx" / "with_image.docx",
            ParserFlags(),
        ).segments
        if segment.kind == "placeholder"
    )
    placeholders.extend(
        segment.text
        for segment in xlsx_parser.parse(
            fixtures_root / "valid" / "xlsx" / "with_formula.xlsx",
            ParserFlags(),
        ).segments
        if segment.kind == "placeholder"
    )
    placeholders.extend(
        segment.text
        for segment in pptx_parser.parse(
            fixtures_root / "valid" / "pptx" / "with_table_image.pptx",
            ParserFlags(),
        ).segments
        if segment.kind == "placeholder"
    )

    assert placeholders
    assert all(PLACEHOLDER_RE.fullmatch(value) for value in placeholders)


@pytest.mark.contract
@pytest.mark.parametrize("literal", ["[Image: x]", "[image:x]", "[圖片: x]"])
def test_invalid_placeholder_literals_do_not_match_contract(literal: str) -> None:
    assert PLACEHOLDER_RE.fullmatch(literal) is None
