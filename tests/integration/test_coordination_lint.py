from __future__ import annotations

import json

import pytest

from hks.adapters import core
from hks.cli import app


@pytest.mark.integration
def test_coordination_lint_reports_missing_references(cli_runner, working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    add = cli_runner.invoke(
        app,
        [
            "coord",
            "handoff",
            "add",
            "agent-a",
            "--summary",
            "checked",
            "--next-action",
            "review",
            "--references",
            '[{"type":"wiki_page","value":"missing-page"}]',
        ],
    )
    lint = cli_runner.invoke(app, ["coord", "lint"])

    assert add.exit_code == 0, add.stdout
    assert lint.exit_code == 0, lint.stdout
    findings = json.loads(lint.stdout)["trace"]["steps"][0]["detail"]["findings"]
    assert findings[0]["category"] == "missing_reference"
