from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from hks.adapters.http_server import create_app

ALLOWED_HOST = {"host": "127.0.0.1"}


@pytest.mark.integration
def test_http_security_rejects_invalid_host() -> None:
    response = TestClient(create_app()).post("/lint", json={}, headers={"host": "evil.test"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "HTTP_HOST_FORBIDDEN"


@pytest.mark.integration
def test_http_security_rejects_mutation_when_token_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)

    response = TestClient(create_app()).post("/ingest", json={}, headers=ALLOWED_HOST)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_MUTATION_TOKEN_NOT_CONFIGURED"


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
            "authorization": "Bearer secret-token",
            "origin": "https://example.test",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_BROWSER_REQUEST_FORBIDDEN"


@pytest.mark.integration
def test_http_security_leaves_read_only_lint_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)

    response = TestClient(create_app()).post("/lint", json={}, headers=ALLOWED_HOST)

    assert response.status_code not in {401, 403}
