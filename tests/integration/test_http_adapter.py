from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

from hks.adapters.http_server import app as http_cli
from hks.adapters.http_server import create_app
from hks.core.schema import validate


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _wiki_page_snapshot(ks_root) -> dict[str, bytes]:
    pages_dir = ks_root / "wiki" / "pages"
    return {path.name: path.read_bytes() for path in sorted(pages_dir.glob("*.md"))}


def _queue_files(ks_root) -> list:
    return sorted((ks_root / "writeback" / "queue").glob("*.json"))


def _writeback_step(payload: dict[str, object]) -> dict[str, object]:
    return next(step for step in payload["trace"]["steps"] if step["kind"] == "writeback")


@pytest.mark.integration
def test_http_adapter_query_ingest_lint_endpoints(working_docs, monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    monkeypatch.setenv("HKS_API_INGEST_ROOTS", f"docs={working_docs.parent}")
    client = TestClient(create_app())

    ingest = client.post(
        "/ingest",
        json={"source_root_id": "docs", "path": working_docs.name},
        headers=_headers("secret"),
    )
    assert ingest.status_code == 200
    validate(ingest.json())

    query = client.post(
        "/query",
        json={"question": "Project Atlas summary"},
        headers=_headers("secret"),
    )
    assert query.status_code == 200
    assert query.json()["source"] == ["wiki"]
    validate(query.json())

    lint = client.post("/lint", json={}, headers=_headers("secret"))
    assert lint.status_code == 200
    assert lint.json()["trace"]["steps"][0]["kind"] == "lint_summary"
    validate(lint.json())


@pytest.mark.integration
def test_http_adapter_query_writeback_yes_enqueues_without_wiki_page(
    working_docs,
    tmp_ks_root,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    monkeypatch.setenv("HKS_API_INGEST_ROOTS", f"docs={working_docs.parent}")
    client = TestClient(create_app())

    ingest = client.post(
        "/ingest",
        json={"source_root_id": "docs", "path": working_docs.name},
        headers=_headers("secret"),
    )
    assert ingest.status_code == 200
    before_pages = _wiki_page_snapshot(tmp_ks_root)

    query = client.post(
        "/query",
        json={"question": "Project Atlas summary", "writeback": "yes"},
        headers=_headers("secret"),
    )

    assert query.status_code == 200
    payload = query.json()
    validate(payload)
    writeback_step = _writeback_step(payload)
    assert writeback_step["detail"]["status"] in {
        "enqueued",
        "enqueued-deduped",
        "already-promoted",
    }
    queue_files = _queue_files(tmp_ks_root)
    assert len(queue_files) == 1
    item = json.loads(queue_files[0].read_text(encoding="utf-8"))
    assert item["question"] == "Project Atlas summary"
    assert item["answer"] == payload["answer"]
    assert _wiki_page_snapshot(tmp_ks_root) == before_pages


@pytest.mark.integration
def test_http_adapter_maps_adapter_error_to_status_and_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    client = TestClient(create_app())

    response = client.post(
        "/query",
        json={"question": "Project Atlas summary"},
        headers=_headers("secret"),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOINPUT"
    assert payload["error"]["exit_code"] == 66


@pytest.mark.integration
def test_http_adapter_rejects_non_object_json_with_usage_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    client = TestClient(create_app())

    response = client.post("/lint", json=[], headers=_headers("secret"))

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "USAGE"
    assert payload["error"]["exit_code"] == 2


@pytest.mark.integration
def test_http_adapter_rejects_non_loopback_host_by_default() -> None:
    result = CliRunner().invoke(http_cli, ["--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "non-loopback host requires --allow-non-loopback" in result.output
