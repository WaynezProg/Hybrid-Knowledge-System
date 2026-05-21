from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from hks.adapters.http_server import create_app

ALLOWED_HOST = {"host": "127.0.0.1"}
VALID_BEARER = {"authorization": "Bearer secret-token"}


def _init_empty_runtime(ks_root: Path) -> None:
    (ks_root / "wiki").mkdir(parents=True)
    (ks_root / "vector" / "db").mkdir(parents=True)
    (ks_root / "manifest.json").write_text(
        '{"version":1,"entries":{}}',
        encoding="utf-8",
    )


@pytest.mark.integration
def test_http_security_rejects_invalid_host() -> None:
    response = TestClient(create_app()).post("/lint", json={}, headers={"host": "evil.test"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "HTTP_HOST_FORBIDDEN"
    assert isinstance(payload["error"]["details"], list)


@pytest.mark.integration
@pytest.mark.parametrize("host", ["[::1]evil.test", "127.0.0.1:bad"])
def test_http_security_rejects_malformed_allowed_hosts(host: str) -> None:
    response = TestClient(create_app()).post("/lint", json={}, headers={"host": host})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_HOST_FORBIDDEN"


@pytest.mark.integration
@pytest.mark.parametrize("host", ["127.0.0.1:8766", "localhost:8766", "[::1]:8766"])
def test_http_security_allows_default_hosts_with_ports(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_ks_root: Path,
) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)
    _init_empty_runtime(tmp_ks_root)

    response = TestClient(create_app()).post("/lint", json={}, headers={"host": host})

    assert response.status_code not in {400, 401, 403}


@pytest.mark.integration
def test_http_security_host_allowlist_override_replaces_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_ks_root: Path,
) -> None:
    monkeypatch.setenv("HKS_API_HOST_ALLOWLIST", "api.local")
    _init_empty_runtime(tmp_ks_root)
    client = TestClient(create_app())

    allowed = client.post("/lint", json={}, headers={"host": "api.local:8766"})
    rejected = client.post("/lint", json={}, headers=ALLOWED_HOST)

    assert allowed.status_code not in {400, 401, 403}
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "HTTP_HOST_FORBIDDEN"


@pytest.mark.integration
@pytest.mark.parametrize(
    "path",
    [
        "/ingest",
        "/query",
        "/workspaces/proj-a/query",
        "/pageindex/enrich",
        "/llm/classify",
        "/wiki/synthesize",
        "/graphify/build",
        "/watch/scan",
        "/watch/run",
        "/coord/session",
        "/coord/lease",
        "/coord/handoff",
        "/workspaces",
        "/workspaces/proj-a",
    ],
)
def test_http_security_guards_all_mutating_endpoints(
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)

    response = TestClient(create_app()).post(path, json={}, headers=ALLOWED_HOST)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_MUTATION_TOKEN_NOT_CONFIGURED"


@pytest.mark.integration
def test_http_security_allows_query_to_reach_validation_with_valid_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret-token")

    response = TestClient(create_app()).post(
        "/query",
        json={},
        headers={**ALLOWED_HOST, **VALID_BEARER},
    )

    assert response.status_code not in {401, 403}


@pytest.mark.integration
def test_http_security_requires_matching_bearer_for_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret-token")
    client = TestClient(create_app())

    missing = client.post("/ingest", json={}, headers=ALLOWED_HOST)
    wrong = client.post(
        "/ingest",
        json={},
        headers={**ALLOWED_HOST, "authorization": "Bearer wrong-token"},
    )

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "HTTP_AUTH_REQUIRED"
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "HTTP_AUTH_REQUIRED"


@pytest.mark.integration
def test_http_security_rejects_browser_style_mutation_with_valid_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret-token")

    response = TestClient(create_app()).post(
        "/ingest",
        json={},
        headers={
            **ALLOWED_HOST,
            **VALID_BEARER,
            "origin": "https://example.test",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_BROWSER_REQUEST_FORBIDDEN"


@pytest.mark.integration
@pytest.mark.parametrize("disabled_value", ["0", "false", "no", "off"])
def test_http_security_allows_browser_style_mutation_when_reject_is_disabled(
    disabled_value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret-token")
    monkeypatch.setenv("HKS_API_REJECT_BROWSER_REQUESTS", disabled_value)

    response = TestClient(create_app()).post(
        "/query",
        json={},
        headers={
            **ALLOWED_HOST,
            **VALID_BEARER,
            "origin": "https://example.test",
        },
    )

    assert response.status_code != 403
    payload = response.json()
    assert payload.get("error", {}).get("code") != "HTTP_BROWSER_REQUEST_FORBIDDEN"


@pytest.mark.integration
def test_http_security_leaves_read_only_lint_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)

    response = TestClient(create_app()).post("/lint", json={}, headers=ALLOWED_HOST)

    assert response.status_code not in {401, 403}
