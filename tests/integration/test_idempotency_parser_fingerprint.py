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
