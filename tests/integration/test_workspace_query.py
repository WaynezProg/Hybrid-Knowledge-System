from __future__ import annotations

import json
from pathlib import Path

import pytest

from hks.cli import app


def _ingest(cli_runner, ks_root: Path, source: Path) -> None:
    result = cli_runner.invoke(app, ["ingest", str(source)], env={"KS_ROOT": str(ks_root)})
    assert result.exit_code == 0


@pytest.mark.integration
def test_workspace_query_is_scoped_to_selected_root(
    cli_runner,
    tmp_path,
    valid_fixtures,
) -> None:
    registry = tmp_path / "workspaces.json"
    atlas_root = tmp_path / "atlas-ks"
    borealis_root = tmp_path / "borealis-ks"
    _ingest(cli_runner, atlas_root, valid_fixtures / "project-atlas.txt")
    _ingest(cli_runner, borealis_root, valid_fixtures / "project-borealis.txt")
    assert (
        cli_runner.invoke(
            app,
            [
                "workspace",
                "register",
                "atlas",
                "--ks-root",
                str(atlas_root),
                "--registry-path",
                str(registry),
            ],
        ).exit_code
        == 0
    )
    assert (
        cli_runner.invoke(
            app,
            [
                "workspace",
                "register",
                "borealis",
                "--ks-root",
                str(borealis_root),
                "--registry-path",
                str(registry),
            ],
        ).exit_code
        == 0
    )

    atlas = cli_runner.invoke(
        app,
        [
            "workspace",
            "query",
            "atlas",
            "Atlas",
            "--writeback",
            "no",
            "--registry-path",
            str(registry),
        ],
    )
    borealis = cli_runner.invoke(
        app,
        [
            "workspace",
            "query",
            "borealis",
            "Borealis",
            "--writeback",
            "no",
            "--registry-path",
            str(registry),
        ],
    )

    assert atlas.exit_code == 0
    assert borealis.exit_code == 0
    assert "Atlas" in json.loads(atlas.stdout)["answer"]
    assert "Borealis" in json.loads(borealis.stdout)["answer"]


@pytest.mark.integration
def test_workspace_query_unknown_workspace_returns_noinput(cli_runner, tmp_path) -> None:
    registry = tmp_path / "workspaces.json"

    result = cli_runner.invoke(
        app,
        ["workspace", "query", "missing", "Atlas", "--registry-path", str(registry)],
    )

    assert result.exit_code == 66


@pytest.mark.integration
def test_workspace_query_conflicting_root_returns_usage(
    cli_runner,
    tmp_path,
    valid_fixtures,
) -> None:
    registry = tmp_path / "workspaces.json"
    ks_root = tmp_path / "ks-a"
    other_root = tmp_path / "ks-b"
    _ingest(cli_runner, ks_root, valid_fixtures / "project-atlas.txt")
    assert (
        cli_runner.invoke(
            app,
            [
                "workspace",
                "register",
                "atlas",
                "--ks-root",
                str(ks_root),
                "--registry-path",
                str(registry),
            ],
        ).exit_code
        == 0
    )

    result = cli_runner.invoke(
        app,
        [
            "workspace",
            "query",
            "atlas",
            "Atlas",
            "--registry-path",
            str(registry),
            "--ks-root",
            str(other_root),
        ],
    )

    assert result.exit_code == 2
