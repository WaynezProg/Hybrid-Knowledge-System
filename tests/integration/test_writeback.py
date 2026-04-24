from __future__ import annotations

import json

import pytest

import hks.commands.query as query_command
from hks.cli import app
from hks.writeback.gate import Decision


@pytest.fixture()
def ingested_for_writeback(cli_runner, working_docs):
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0
    return working_docs


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_ask_yes_commits(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        query_command,
        "decide",
        lambda flag, confidence, is_tty: Decision(action="commit", status="committed"),
    )

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(step["kind"] == "writeback" for step in payload["trace"]["steps"])
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 11


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_ask_no_declines(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        query_command,
        "decide",
        lambda flag, confidence, is_tty: Decision(action="decline", status="declined"),
    )

    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=ask"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_auto_commits_high_confidence_by_default(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "auto-committed"
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 11


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_yes_overrides_non_tty(cli_runner, ingested_for_writeback, tmp_ks_root) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=yes"])

    assert result.exit_code == 0
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 11


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_no_overrides_and_skips_commit(
    cli_runner, ingested_for_writeback, tmp_ks_root
) -> None:
    result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=no"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["trace"]["steps"][-1]["detail"]["status"] == "declined"
    assert len(list((tmp_ks_root / "wiki" / "pages").glob("*.md"))) == 10


@pytest.mark.integration
@pytest.mark.us3
def test_writeback_slug_collision_uses_suffix(
    cli_runner,
    ingested_for_writeback,
    tmp_ks_root,
) -> None:
    collision = tmp_ks_root / "wiki" / "pages" / "project-a-summary.md"
    collision.write_text(
        (
            "---\n"
            "slug: project-a-summary\n"
            "title: Project A Summary\n"
            "summary: existing\n"
            "source: <writeback>\n"
            "origin: writeback\n"
            "updated_at: 2026-04-24T00:00:00+00:00\n"
            "---\n\n"
            "# Project A Summary\n\n"
            "existing\n"
        ),
        encoding="utf-8",
    )

    result = cli_runner.invoke(app, ["query", "Project A summary", "--writeback=yes"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    writeback_step = next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")
    assert writeback_step["detail"]["slug"] == "project-a-summary-2"
    page_text = (tmp_ks_root / "wiki" / "pages" / "project-a-summary-2.md").read_text(
        encoding="utf-8"
    )
    assert "## Related" in page_text
