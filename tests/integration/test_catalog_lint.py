from __future__ import annotations

import json

import pytest

from hks.cli import app


@pytest.mark.integration
def test_lint_detects_corrupt_workspace_registry(cli_runner, tmp_path, working_docs) -> None:
    registry = tmp_path / "workspaces.json"
    registry.write_text("{", encoding="utf-8")
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0

    result = cli_runner.invoke(app, ["lint"], env={"HKS_WORKSPACE_REGISTRY": str(registry)})

    assert result.exit_code == 0
    findings = json.loads(result.stdout)["trace"]["steps"][0]["detail"]["findings"]
    assert any(finding["category"] == "workspace_registry_corrupt" for finding in findings)


@pytest.mark.integration
def test_lint_detects_missing_workspace_root(cli_runner, tmp_path, working_docs) -> None:
    registry = tmp_path / "workspaces.json"
    assert cli_runner.invoke(app, ["ingest", str(working_docs)]).exit_code == 0
    assert (
        cli_runner.invoke(
            app,
            [
                "workspace",
                "register",
                "missing",
                "--ks-root",
                str(tmp_path / "missing"),
                "--registry-path",
                str(registry),
            ],
        ).exit_code
        == 0
    )

    result = cli_runner.invoke(app, ["lint"], env={"HKS_WORKSPACE_REGISTRY": str(registry)})

    findings = json.loads(result.stdout)["trace"]["steps"][0]["detail"]["findings"]
    assert any(finding["category"] == "workspace_root_missing" for finding in findings)

