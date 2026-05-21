from __future__ import annotations

from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


def test_graphify_cli_core_and_http_preview_are_semantically_consistent(
    working_docs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))

    direct = core.hks_graphify_build(mode="preview")
    http = TestClient(create_app()).post(
        "/graphify/build",
        json={"mode": "preview"},
        headers=_headers("secret"),
    ).json()

    direct_detail = direct["trace"]["steps"][0]["detail"]
    http_detail = http["trace"]["steps"][0]["detail"]
    assert direct["source"] == http["source"]
    assert direct_detail["node_count"] == http_detail["node_count"]
    assert direct_detail["edge_count"] == http_detail["edge_count"]
    assert direct_detail["community_count"] == http_detail["community_count"]
