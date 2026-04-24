from __future__ import annotations

import json

import pytest

from hks.cli import app


@pytest.mark.contract
def test_runtime_outputs_never_emit_graph(cli_runner, working_docs, tmp_ks_root) -> None:
    ingest_result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert ingest_result.exit_code == 0

    query_result = cli_runner.invoke(app, ["query", "summary Atlas", "--writeback=no"])
    assert query_result.exit_code == 0

    lint_result = cli_runner.invoke(app, ["lint"])
    assert lint_result.exit_code == 0

    for raw in (ingest_result.stdout, query_result.stdout, lint_result.stdout):
        payload = json.loads(raw)
        assert "graph" not in payload["source"]
        assert payload["trace"]["route"] != "graph"

    assert not (tmp_ks_root / "graph").exists()
