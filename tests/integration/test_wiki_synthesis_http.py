from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


@pytest.mark.integration
def test_http_wiki_synthesize_preview(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))
    core.hks_llm_classify(source_relpath="project-atlas.txt", mode="store")
    client = TestClient(create_app())

    response = client.post(
        "/wiki/synthesize",
        json={
            "source_relpath": "project-atlas.txt",
            "target_slug": "project-atlas-synthesis",
            "provider": "fake",
        },
        headers=_headers("secret"),
    )

    assert response.status_code == 200
    assert response.json()["trace"]["steps"][0]["kind"] == "wiki_synthesis_summary"


@pytest.mark.integration
def test_http_wiki_synthesize_error_uses_adapter_envelope(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post(
        "/wiki/synthesize",
        json={"source_relpath": "project-atlas.txt", "provider": "hosted-example"},
        headers=_headers("secret"),
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "USAGE"
