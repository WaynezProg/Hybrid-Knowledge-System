from __future__ import annotations

from pathlib import Path

import pytest

from hks.adapters.core import hks_workspace_ingest_session_memory, hks_workspace_query
from hks.adapters.models import AdapterToolError


@pytest.mark.integration
def test_workspace_ingest_session_memory_auto_registers_and_ingests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root = tmp_path / "export"
    ks_base = tmp_path / "ks-base"
    registry = tmp_path / "workspaces.json"
    workspace_id = "demo"
    daily = export_root / workspace_id / "daily" / "2026-05-31.md"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "---\nhks_type: session_daily\n"
        "date: 2026-05-31\n"
        "source_domain: session_memory\n"
        "generator: session2memory\n"
        "workspace_id: demo\n"
        "---\n# 2026-05-31\n\n- item\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HKS_SESSION2MEMORY_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("HKS_KS_ROOT_BASE", str(ks_base))
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(registry))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")

    payload = hks_workspace_ingest_session_memory(
        workspace_id=workspace_id,
        path="daily/2026-05-31.md",
    )

    assert payload["trace"]["steps"]
    assert (ks_base / workspace_id / "manifest.json").exists()


@pytest.mark.integration
def test_rejects_harness_like_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root = tmp_path / "export"
    ks_base = tmp_path / "ks-base"
    registry = tmp_path / "workspaces.json"
    workspace_id = "demo"
    bad = export_root / workspace_id / "raw.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# transcript dump\n", encoding="utf-8")
    monkeypatch.setenv("HKS_SESSION2MEMORY_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("HKS_KS_ROOT_BASE", str(ks_base))
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(registry))

    with pytest.raises(AdapterToolError) as exc:
        hks_workspace_ingest_session_memory(
            workspace_id=workspace_id,
            path="raw.md",
        )

    assert exc.value.error.code == "INGEST_SOURCE_DISALLOWED"


@pytest.mark.integration
def test_ingest_then_workspace_query_returns_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root = tmp_path / "export"
    ks_base = tmp_path / "ks-base"
    registry = tmp_path / "workspaces.json"
    workspace_id = "demo"
    marker = "UNIQUE_AGENT_INGEST_MARKER_42"
    daily = export_root / workspace_id / "daily" / "2026-05-31.md"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "---\nhks_type: session_daily\n"
        "date: 2026-05-31\n"
        "source_domain: session_memory\n"
        "generator: session2memory\n"
        "workspace_id: demo\n"
        "---\n"
        f"# 2026-05-31\n\n- [note] {marker}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HKS_SESSION2MEMORY_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("HKS_KS_ROOT_BASE", str(ks_base))
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(registry))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")

    hks_workspace_ingest_session_memory(
        workspace_id=workspace_id,
        path="daily/2026-05-31.md",
    )
    response = hks_workspace_query(
        workspace_id=workspace_id,
        question=marker,
        writeback="no",
    )

    assert response["evidence"]
    assert marker in response["answer"] or any(
        marker in item.get("quote", "") for item in response["evidence"]
    )
