"""Unit tests for `detect_source_format` (suffix + content sniffing)."""

from __future__ import annotations

import shutil

import pytest

from hks.core.manifest import detect_source_format, source_format_from_path


@pytest.mark.unit
def test_detect_txt_by_suffix_only(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    assert detect_source_format(path) == "txt"


@pytest.mark.unit
def test_detect_md_by_suffix_only(tmp_path) -> None:
    path = tmp_path / "a.md"
    path.write_text("# hi", encoding="utf-8")
    assert detect_source_format(path) == "md"


@pytest.mark.unit
def test_detect_valid_pdf_requires_magic(tmp_path) -> None:
    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF-1.4\nfake body")
    assert detect_source_format(good) == "pdf"


@pytest.mark.unit
def test_detect_mislabeled_pdf_returns_none(tmp_path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a valid pdf")
    assert detect_source_format(bad) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("suffix", "fixture_name"),
    [("docx", "plain.docx"), ("xlsx", "single_sheet.xlsx"), ("pptx", "plain.pptx")],
)
def test_detect_valid_office_requires_ooxml_main_part(
    fixtures_root, tmp_path, suffix: str, fixture_name: str
) -> None:
    good = tmp_path / f"a.{suffix}"
    shutil.copy2(fixtures_root / "valid" / suffix / fixture_name, good)
    assert detect_source_format(good) == suffix


@pytest.mark.unit
@pytest.mark.parametrize("suffix", ["docx", "xlsx", "pptx"])
def test_detect_mislabeled_office_returns_none(tmp_path, suffix: str) -> None:
    bad = tmp_path / f"b.{suffix}"
    bad.write_bytes(b"not a zip container")
    assert detect_source_format(bad) is None


@pytest.mark.unit
@pytest.mark.parametrize("suffix", ["docx", "xlsx", "pptx"])
def test_detect_zip_without_required_part_returns_none(tmp_path, suffix: str) -> None:
    bad = tmp_path / f"broken.{suffix}"
    import zipfile

    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    assert detect_source_format(bad) is None


@pytest.mark.unit
def test_detect_unknown_suffix(tmp_path) -> None:
    path = tmp_path / "x.csv"
    path.write_text("a,b", encoding="utf-8")
    assert detect_source_format(path) is None
    assert source_format_from_path(path) is None


@pytest.mark.unit
def test_suffix_helper_accepts_office_extensions(tmp_path) -> None:
    for suffix in ("docx", "xlsx", "pptx"):
        path = tmp_path / f"x.{suffix}"
        path.write_bytes(b"PK\x03\x04")
        assert source_format_from_path(path) == suffix
