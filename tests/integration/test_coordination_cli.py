from __future__ import annotations

import json

import pytest

from hks.cli import app


def _ingest(cli_runner, working_docs) -> None:
    result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert result.exit_code == 0, result.stdout


def _payload(result) -> dict:
    assert result.stdout
    return json.loads(result.stdout)


@pytest.mark.integration
def test_coord_cli_session_lease_handoff_status_flow(cli_runner, working_docs, tmp_ks_root) -> None:
    _ingest(cli_runner, working_docs)

    session = cli_runner.invoke(app, ["coord", "session", "start", "agent-a"])
    assert session.exit_code == 0, session.stdout
    session_id = _payload(session)["trace"]["steps"][0]["detail"]["sessions"][0]["session_id"]

    lease = cli_runner.invoke(
        app,
        [
            "coord",
            "lease",
            "claim",
            "agent-a",
            "wiki:atlas",
            "--session-id",
            session_id,
        ],
    )
    assert lease.exit_code == 0, lease.stdout

    handoff = cli_runner.invoke(
        app,
        [
            "coord",
            "handoff",
            "add",
            "agent-a",
            "--resource-key",
            "wiki:atlas",
            "--summary",
            "已完成索引檢查",
            "--next-action",
            "請複核 lint 結果",
        ],
    )
    assert handoff.exit_code == 0, handoff.stdout

    status = cli_runner.invoke(app, ["coord", "status", "--agent-id", "agent-a"])
    payload = _payload(status)
    detail = payload["trace"]["steps"][0]["detail"]

    assert status.exit_code == 0
    assert payload["trace"]["steps"][0]["kind"] == "coordination_summary"
    assert detail["sessions"][0]["agent_id"] == "agent-a"
    assert detail["leases"][0]["resource_key"] == "wiki:atlas"
    assert detail["handoffs"][0]["resource_key"] == "wiki:atlas"

    renew = cli_runner.invoke(app, ["coord", "lease", "renew", "agent-a", "wiki:atlas"])
    release = cli_runner.invoke(app, ["coord", "lease", "release", "agent-a", "wiki:atlas"])
    listed = cli_runner.invoke(app, ["coord", "handoff", "list", "agent-a"])

    assert renew.exit_code == 0, renew.stdout
    assert release.exit_code == 0, release.stdout
    assert _payload(listed)["trace"]["steps"][0]["detail"]["handoffs"][0]["summary"]


@pytest.mark.integration
def test_coord_cli_conflicting_lease_returns_structured_error(
    cli_runner,
    working_docs,
    tmp_ks_root,
) -> None:
    _ingest(cli_runner, working_docs)
    first = cli_runner.invoke(app, ["coord", "lease", "claim", "agent-a", "wiki:atlas"])
    second = cli_runner.invoke(app, ["coord", "lease", "claim", "agent-b", "wiki:atlas"])

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 1
    payload = _payload(second)
    assert payload["trace"]["steps"][0]["detail"]["conflicts"][0]["owner_agent_id"] == "agent-a"


@pytest.mark.integration
def test_coord_cli_uninitialized_runtime_returns_noinput(cli_runner) -> None:
    result = cli_runner.invoke(app, ["coord", "status"])

    assert result.exit_code == 66
    assert _payload(result)["trace"]["steps"][0]["detail"]["code"] == "NOINPUT"


@pytest.mark.integration
def test_coord_cli_invalid_agent_id_returns_usage(cli_runner, working_docs) -> None:
    _ingest(cli_runner, working_docs)

    result = cli_runner.invoke(app, ["coord", "session", "start", "bad id"])

    assert result.exit_code == 2
    assert _payload(result)["trace"]["steps"][0]["detail"]["code"] == "USAGE"
