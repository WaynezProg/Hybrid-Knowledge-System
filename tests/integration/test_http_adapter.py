from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from hks.adapters.http_server import app as http_cli
from hks.adapters.http_server import create_app
from hks.core.schema import validate


@pytest.mark.integration
def test_http_adapter_query_ingest_lint_endpoints(working_docs) -> None:
    client = TestClient(create_app())

    ingest = client.post("/ingest", json={"path": str(working_docs)})
    assert ingest.status_code == 200
    validate(ingest.json())

    query = client.post("/query", json={"question": "Project Atlas summary"})
    assert query.status_code == 200
    assert query.json()["source"] == ["wiki"]
    validate(query.json())

    lint = client.post("/lint", json={})
    assert lint.status_code == 200
    assert lint.json()["trace"]["steps"][0]["kind"] == "lint_summary"
    validate(lint.json())


@pytest.mark.integration
def test_http_adapter_maps_adapter_error_to_status_and_envelope() -> None:
    client = TestClient(create_app())

    response = client.post("/query", json={"question": "Project Atlas summary"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOINPUT"
    assert payload["error"]["exit_code"] == 66


@pytest.mark.integration
def test_http_adapter_rejects_non_object_json_with_usage_envelope() -> None:
    client = TestClient(create_app())

    response = client.post("/lint", json=[])

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert payload["error"]["exit_code"] == 2


@pytest.mark.integration
def test_http_adapter_rejects_non_loopback_host_by_default() -> None:
    result = CliRunner().invoke(http_cli, ["--host", "0.0.0.0"], env={"COLUMNS": "200"})

    assert result.exit_code != 0
    assert "non-loopback host requires --allow-non-loopback" in result.output
