from __future__ import annotations

import json

import pytest

from hks.cli import app
from hks.ingest import fingerprint


@pytest.mark.integration
@pytest.mark.us3
def test_parser_library_version_bump_triggers_reingest(
    cli_runner,
    working_office_docs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert first.exit_code == 0, first.stdout

    original_version = fingerprint.version

    def fake_version(package: str) -> str:
        if package == "openpyxl":
            return "9.9.9"
        return original_version(package)

    monkeypatch.setattr(fingerprint, "version", fake_version)

    second = cli_runner.invoke(app, ["ingest", str(working_office_docs)])
    assert second.exit_code == 0, second.stdout
    payload = json.loads(second.stdout)
    assert sorted(payload["trace"]["steps"][0]["detail"]["updated"]) == [
        "xlsx/multi_sheet.xlsx",
        "xlsx/single_sheet.xlsx",
        "xlsx/with_formula.xlsx",
    ]


@pytest.mark.integration
@pytest.mark.us1
def test_image_ocr_engine_signature_bump_triggers_reingest(
    cli_runner,
    working_image_docs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = cli_runner.invoke(app, ["ingest", str(working_image_docs)])
    assert first.exit_code == 0, first.stdout

    monkeypatch.setattr(
        fingerprint,
        "ocr_engine_signature",
        lambda: "tesseract-9.9.9+eng+chi_tra",
    )

    second = cli_runner.invoke(app, ["ingest", str(working_image_docs)])
    assert second.exit_code == 0, second.stdout
    payload = json.loads(second.stdout)
    assert sorted(payload["trace"]["steps"][0]["detail"]["updated"]) == [
        "atlas-dependency.png",
        "mixed-status.jpg",
        "multi-column.jpeg",
        "rotated-notice.png",
        "zh-ops.png",
    ]
