from __future__ import annotations

import json

import anyio

from hks.adapters.mcp_server import create_server
from hks.cli import app
from hks.core.schema import validate


def test_cli_and_mcp_share_user_registry_from_unrelated_directories(
    cli_runner, monkeypatch, tmp_path
) -> None:
    registry = tmp_path / "registry.json"
    result = cli_runner.invoke(
        app,
        [
            "workspace",
            "register",
            "demo",
            "--ks-root",
            str(tmp_path / "data"),
            "--registry-path",
            str(registry),
        ],
    )
    assert result.exit_code == 0, result.output
    config = tmp_path / "user-config" / "hks"
    config.mkdir(parents=True)
    (config / "hks.json").write_text(json.dumps({"runtime": {"workspace_registry": str(registry)}}))
    for key in ("HKS_CONFIG_ENV", "HKS_CONFIG_FILE", "HKS_REPO_ROOT", "HKS_WORKSPACE_REGISTRY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config.parent))

    async def call_mcp():
        blocks = await create_server().call_tool("hks_workspace_list", {})
        return json.loads(blocks[0].text)

    for name in ("parent", "other-project"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.chdir(directory)
        cli = cli_runner.invoke(app, ["workspace", "list"])
        assert cli.exit_code == 0, cli.output
        cli_payload = json.loads(cli.output)
        mcp_payload = anyio.run(call_mcp)
        validate(mcp_payload)
        cli_detail = cli_payload["trace"]["steps"][0]["detail"]
        mcp_detail = mcp_payload["trace"]["steps"][0]["detail"]
        assert cli_detail == mcp_detail
        assert cli_detail["total_count"] == 1
        assert cli_detail["workspaces"][0]["id"] == "demo"
