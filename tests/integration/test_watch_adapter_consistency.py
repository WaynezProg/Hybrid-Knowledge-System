from __future__ import annotations

import json

from starlette.testclient import TestClient

from hks.adapters import core
from hks.adapters.http_server import create_app
from hks.cli import app


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


def test_watch_cli_core_and_http_scan_are_semantically_consistent(
    cli_runner,
    working_docs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    core.hks_ingest(path=str(working_docs))

    cli_payload = json.loads(
        cli_runner.invoke(app, ["watch", "scan", "--source-root", str(working_docs)]).stdout
    )
    direct = core.hks_watch_scan(source_roots=[str(working_docs)])
    http = TestClient(create_app()).post(
        "/watch/scan",
        json={"source_roots": [str(working_docs)]},
        headers=_headers("secret"),
    ).json()

    assert cli_payload["source"] == direct["source"] == http["source"]
    assert cli_payload["trace"]["route"] == direct["trace"]["route"] == http["trace"]["route"]
    assert (
        cli_payload["trace"]["steps"][0]["detail"]["source_counts"]
        == direct["trace"]["steps"][0]["detail"]["source_counts"]
        == http["trace"]["steps"][0]["detail"]["source_counts"]
    )
