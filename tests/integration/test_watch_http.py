from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


@pytest.mark.integration
def test_http_watch_scan(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post("/watch/scan", json={"source_roots": [str(working_docs)]})

    assert response.status_code == 200
    assert response.json()["trace"]["steps"][0]["kind"] == "watch_summary"


@pytest.mark.integration
def test_http_watch_status(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    core.hks_watch_scan(source_roots=[str(working_docs)])
    client = TestClient(create_app())

    response = client.post("/watch/status", json={})

    assert response.status_code == 200
    assert response.json()["trace"]["steps"][0]["detail"]["operation"] == "status"


@pytest.mark.integration
def test_http_watch_bad_mode_uses_adapter_envelope(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post("/watch/run", json={"mode": "apply"})

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "USAGE"
