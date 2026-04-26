from __future__ import annotations

import json

from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app
from hks.cli import app


def test_source_list_cli_core_and_http_are_semantically_consistent(
    cli_runner,
    working_docs,
) -> None:
    core.hks_ingest(path=str(working_docs))

    cli_payload = json.loads(cli_runner.invoke(app, ["source", "list"]).stdout)
    direct = core.hks_source_list()
    http = TestClient(create_app()).post("/catalog/sources", json={}).json()

    cli_detail = cli_payload["trace"]["steps"][0]["detail"]
    direct_detail = direct["trace"]["steps"][0]["detail"]
    http_detail = http["trace"]["steps"][0]["detail"]
    assert cli_detail["total_count"] == direct_detail["total_count"] == http_detail["total_count"]
    assert cli_detail["command"] == direct_detail["command"] == http_detail["command"]
    assert (
        cli_detail["sources"][0]["relpath"]
        == direct_detail["sources"][0]["relpath"]
        == http_detail["sources"][0]["relpath"]
    )


def test_workspace_list_cli_core_and_http_are_semantically_consistent(
    cli_runner,
    tmp_path,
    working_docs,
) -> None:
    registry = tmp_path / "workspaces.json"
    core.hks_ingest(path=str(working_docs))
    core.hks_workspace_register(
        workspace_id="proj-a",
        ks_root=str(tmp_path / "ks"),
        registry_path=str(registry),
    )

    cli_payload = json.loads(
        cli_runner.invoke(
            app,
            ["workspace", "list", "--registry-path", str(registry)],
        ).stdout
    )
    direct = core.hks_workspace_list(registry_path=str(registry))
    http = TestClient(create_app()).post(
        "/workspaces",
        json={"action": "list", "registry_path": str(registry)},
    ).json()

    assert (
        cli_payload["trace"]["steps"][0]["detail"]["total_count"]
        == direct["trace"]["steps"][0]["detail"]["total_count"]
        == http["trace"]["steps"][0]["detail"]["total_count"]
        == 1
    )

