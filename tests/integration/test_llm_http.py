from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from hks.adapters import core
from hks.adapters.http_server import app as http_cli
from hks.adapters.http_server import create_app
from hks.core.schema import validate


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


@pytest.mark.integration
def test_http_llm_classify_preview(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post(
        "/llm/classify",
        json={"source_relpath": "project-atlas.txt", "provider": "fake"},
        headers=_headers("secret"),
    )

    assert response.status_code == 200
    validate(response.json())
    assert response.json()["trace"]["steps"][0]["kind"] == "llm_extraction_summary"


@pytest.mark.integration
def test_http_llm_classify_error_uses_adapter_envelope(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post(
        "/llm/classify",
        json={"source_relpath": "project-atlas.txt", "provider": "hosted-example"},
        headers=_headers("secret"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"


@pytest.mark.integration
def test_http_llm_rejects_non_loopback_host_by_default() -> None:
    result = CliRunner().invoke(http_cli, ["--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "non-loopback host requires --allow-non-loopback" in result.output
