from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from hks.adapters.http_server import create_app
from hks.core.manifest import load_manifest

AUTH_HEADERS = {
    "host": "127.0.0.1",
    "authorization": "Bearer secret",
}


def _client(monkeypatch: pytest.MonkeyPatch, roots: str | None) -> TestClient:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    if roots is None:
        monkeypatch.delenv("HKS_API_INGEST_ROOTS", raising=False)
    else:
        monkeypatch.setenv("HKS_API_INGEST_ROOTS", roots)
    return TestClient(create_app())


def _post_ingest(client: TestClient, payload: dict[str, Any]):
    return client.post("/ingest", json=payload, headers=AUTH_HEADERS)


def _write_doc(root: Path, relpath: str, text: str = "Atlas project note") -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _assert_no_path_leak(payload: dict[str, Any], *paths: Path) -> None:
    error = payload["error"]
    serialized = f"{error['message']} {error['details']}"
    for path in paths:
        assert str(path) not in serialized


@pytest.mark.integration
def test_http_ingest_allows_relative_path_under_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    _write_doc(source_root, "notes/project.md")
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "notes/project.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 200
    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert "notes/project.md" in manifest.entries


@pytest.mark.integration
def test_http_single_file_ingest_preserves_source_root_relative_collision_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    _write_doc(source_root, "a/same.md", "alpha")
    _write_doc(source_root, "b/same.md", "bravo")
    client = _client(monkeypatch, f"docs={source_root}")

    first = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "a/same.md", "ks_root": str(tmp_ks_root)},
    )
    second = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "b/same.md", "ks_root": str(tmp_ks_root)},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert "a/same.md" in manifest.entries
    assert "b/same.md" in manifest.entries
    assert "same.md" not in manifest.entries


@pytest.mark.integration
def test_http_ingest_rejects_absolute_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    doc = _write_doc(source_root, "project.md")
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": str(doc), "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_PATH_FORBIDDEN"


@pytest.mark.integration
def test_http_ingest_rejects_parent_escape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    _write_doc(tmp_path, "secret.md")
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "../secret.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_PATH_FORBIDDEN"


@pytest.mark.integration
def test_http_ingest_rejects_top_level_symlink_escape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    outside = _write_doc(tmp_path / "outside", "secret.md")
    source_root.mkdir()
    (source_root / "linked.md").symlink_to(outside)
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "linked.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_PATH_FORBIDDEN"


@pytest.mark.integration
def test_http_ingest_rejects_unavailable_configured_root_without_path_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    missing_root = tmp_path / "missing"
    client = _client(monkeypatch, f"docs={missing_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "project.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "HTTP_INGEST_ROOT_UNAVAILABLE"
    _assert_no_path_leak(payload, tmp_path, missing_root)


@pytest.mark.integration
def test_http_ingest_rejects_missing_target_without_path_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "missing.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "HTTP_INGEST_PATH_NOT_FOUND"
    _assert_no_path_leak(payload, tmp_path, source_root)


@pytest.mark.integration
def test_http_ingest_rejects_broken_symlink_without_path_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "broken.md").symlink_to(tmp_path / "missing-target.md")
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": "broken.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "HTTP_INGEST_PATH_NOT_FOUND"
    _assert_no_path_leak(payload, tmp_path, source_root)


@pytest.mark.integration
def test_http_directory_ingest_skips_blocked_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    _write_doc(source_root, "public.md", "public note")
    _write_doc(source_root, ".ssh/secret.md", "private key note")
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": ".", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 200
    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert "public.md" in manifest.entries
    assert ".ssh/secret.md" not in manifest.entries


@pytest.mark.integration
def test_http_directory_ingest_skips_recursive_symlink_file_escape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    outside = _write_doc(tmp_path / "outside", "secret.md")
    _write_doc(source_root, "public.md", "public note")
    (source_root / "nested").mkdir()
    (source_root / "nested" / "linked.md").symlink_to(outside)
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(
        client,
        {"source_root_id": "docs", "path": ".", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 200
    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert "public.md" in manifest.entries
    assert "nested/linked.md" not in manifest.entries


@pytest.mark.integration
def test_http_ingest_rejects_when_roots_not_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_ks_root: Path
) -> None:
    client = _client(monkeypatch, None)

    response = _post_ingest(client, {"path": "project.md", "ks_root": str(tmp_ks_root)})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_INGEST_ROOTS_NOT_CONFIGURED"


@pytest.mark.integration
def test_http_ingest_requires_source_root_id_when_multiple_roots_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    client = _client(monkeypatch, f"a={tmp_path / 'a'},b={tmp_path / 'b'}")

    response = _post_ingest(client, {"path": "project.md", "ks_root": str(tmp_ks_root)})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_SOURCE_ROOT_REQUIRED"


@pytest.mark.integration
def test_http_ingest_rejects_unknown_source_root_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    client = _client(monkeypatch, f"docs={tmp_path / 'source'}")

    response = _post_ingest(
        client,
        {"source_root_id": "missing", "path": "project.md", "ks_root": str(tmp_ks_root)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_SOURCE_ROOT_UNKNOWN"


@pytest.mark.integration
def test_http_ingest_allows_single_root_without_source_root_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tmp_ks_root: Path
) -> None:
    source_root = tmp_path / "source"
    _write_doc(source_root, "project.md")
    client = _client(monkeypatch, f"docs={source_root}")

    response = _post_ingest(client, {"path": "project.md", "ks_root": str(tmp_ks_root)})

    assert response.status_code == 200
    manifest = load_manifest(tmp_ks_root / "manifest.json")
    assert "project.md" in manifest.entries
