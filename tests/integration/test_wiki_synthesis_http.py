from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


@pytest.mark.integration
def test_http_wiki_synthesize_preview(working_docs) -> None:
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
    )

    assert response.status_code == 200
    assert response.json()["trace"]["steps"][0]["kind"] == "wiki_synthesis_summary"


@pytest.mark.integration
def test_http_wiki_synthesize_error_uses_adapter_envelope(working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    client = TestClient(create_app())

    response = client.post(
        "/wiki/synthesize",
        json={"source_relpath": "project-atlas.txt", "provider": "hosted-example"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "USAGE"
