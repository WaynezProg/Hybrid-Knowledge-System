from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


@pytest.mark.integration
def test_http_graphify_preview(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post("/graphify/build", json={"mode": "preview", "provider": "fake"})

    assert response.status_code == 200
    assert response.json()["trace"]["steps"][0]["kind"] == "graphify_summary"


@pytest.mark.integration
def test_http_graphify_hosted_provider_error_uses_adapter_envelope(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post(
        "/graphify/build",
        json={"mode": "preview", "provider": "hosted-example"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "USAGE"
