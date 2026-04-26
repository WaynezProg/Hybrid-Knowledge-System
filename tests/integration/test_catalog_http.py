from __future__ import annotations

from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


def test_http_catalog_sources_and_workspace_query(tmp_path, working_docs) -> None:
    registry = tmp_path / "workspaces.json"
    ks_root = tmp_path / "ks"
    core.hks_ingest(path=str(working_docs), ks_root=str(ks_root))
    client = TestClient(create_app())

    sources = client.post("/catalog/sources", json={"ks_root": str(ks_root)}).json()
    assert sources["trace"]["steps"][0]["detail"]["total_count"] > 0

    detail = client.post(
        "/catalog/sources/project-atlas.txt",
        json={"ks_root": str(ks_root)},
    ).json()
    assert detail["trace"]["steps"][0]["detail"]["source"]["relpath"] == "project-atlas.txt"

    registered = client.post(
        "/workspaces",
        json={
            "action": "register",
            "workspace_id": "proj-a",
            "ks_root": str(ks_root),
            "registry_path": str(registry),
        },
    ).json()
    assert registered["trace"]["steps"][0]["detail"]["workspace_id"] == "proj-a"

    query = client.post(
        "/workspaces/proj-a/query",
        json={"question": "Atlas", "writeback": "no", "registry_path": str(registry)},
    ).json()
    assert query["source"]


def test_http_catalog_error_uses_adapter_envelope() -> None:
    response = TestClient(create_app()).post(
        "/workspaces",
        json={"action": "register", "workspace_id": "../bad", "ks_root": "/tmp/ks"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["exit_code"] == 2

