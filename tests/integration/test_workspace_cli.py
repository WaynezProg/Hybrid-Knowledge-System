from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.cli import app


def _ingest(cli_runner, ks_root: Path, source: Path) -> None:
    result = cli_runner.invoke(app, ["ingest", str(source)], env={"KS_ROOT": str(ks_root)})
    assert result.exit_code == 0


@pytest.mark.integration
def test_workspace_register_list_show_use_and_remove(
    cli_runner,
    tmp_path,
    working_docs,
) -> None:
    registry = tmp_path / "workspaces.json"
    ks_root = tmp_path / "project-a-ks"
    _ingest(cli_runner, ks_root, working_docs)

    register = cli_runner.invoke(
        app,
        [
            "workspace",
            "register",
            "proj-a",
            "--ks-root",
            str(ks_root),
            "--label",
            "Project A",
            "--registry-path",
            str(registry),
        ],
    )
    assert register.exit_code == 0

    listed = cli_runner.invoke(app, ["workspace", "list", "--registry-path", str(registry)])
    assert listed.exit_code == 0
    detail = json.loads(listed.stdout)["trace"]["steps"][0]["detail"]
    assert detail["command"] == "workspace.list"
    assert detail["workspaces"][0]["id"] == "proj-a"
    assert detail["workspaces"][0]["status"] == "ready"
    assert detail["workspaces"][0]["source_count"] > 0

    show = cli_runner.invoke(app, ["workspace", "show", "proj-a", "--registry-path", str(registry)])
    assert show.exit_code == 0

    use = cli_runner.invoke(app, ["workspace", "use", "proj-a", "--registry-path", str(registry)])
    assert use.exit_code == 0
    use_detail = json.loads(use.stdout)["trace"]["steps"][0]["detail"]
    assert use_detail["export_command"].startswith("export KS_ROOT=")

    removed = cli_runner.invoke(
        app,
        ["workspace", "remove", "proj-a", "--registry-path", str(registry)],
    )
    assert removed.exit_code == 0


@pytest.mark.integration
def test_workspace_list_marks_missing_and_duplicate_roots(cli_runner, tmp_path) -> None:
    registry = tmp_path / "workspaces.json"
    missing_root = tmp_path / "missing"

    for workspace_id in ("proj-a", "proj-b"):
        result = cli_runner.invoke(
            app,
            [
                "workspace",
                "register",
                workspace_id,
                "--ks-root",
                str(missing_root),
                "--registry-path",
                str(registry),
            ],
        )
        assert result.exit_code == 0

    listed = cli_runner.invoke(app, ["workspace", "list", "--registry-path", str(registry)])

    assert listed.exit_code == 0
    statuses = json.loads(listed.stdout)["trace"]["steps"][0]["detail"]["workspaces"]
    assert {status["status"] for status in statuses} == {"missing"}


@pytest.mark.integration
def test_workspace_corrupt_registry_returns_dataerr(cli_runner, tmp_path) -> None:
    registry = tmp_path / "workspaces.json"
    registry.write_text("{", encoding="utf-8")

    result = cli_runner.invoke(app, ["workspace", "list", "--registry-path", str(registry)])

    assert result.exit_code == 65


@pytest.mark.integration
def test_workspace_register_conflict_requires_force(cli_runner, tmp_path, working_docs) -> None:
    registry = tmp_path / "workspaces.json"
    ks_root = tmp_path / "ks-a"
    other_root = tmp_path / "ks-b"
    _ingest(cli_runner, ks_root, working_docs)
    _ingest(cli_runner, other_root, working_docs)
    assert (
        cli_runner.invoke(
            app,
            [
                "workspace",
                "register",
                "proj-a",
                "--ks-root",
                str(ks_root),
                "--registry-path",
                str(registry),
            ],
        ).exit_code
        == 0
    )

    conflict = cli_runner.invoke(
        app,
        [
            "workspace",
            "register",
            "proj-a",
            "--ks-root",
            str(other_root),
            "--registry-path",
            str(registry),
        ],
    )
    assert conflict.exit_code == 66

    forced = cli_runner.invoke(
        app,
        [
            "workspace",
            "register",
            "proj-a",
            "--ks-root",
            str(other_root),
            "--registry-path",
            str(registry),
            "--force",
        ],
    )
    assert forced.exit_code == 0
    detail = json.loads(forced.stdout)["trace"]["steps"][0]["detail"]
    assert detail["previous_root"] == ks_root.as_posix()
