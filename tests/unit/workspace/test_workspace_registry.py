from __future__ import annotations

import pytest

from hks.errors import KSError
from hks.workspace.models import WorkspaceRecord, WorkspaceRegistry
from hks.workspace.registry import load_registry, save_registry


def test_workspace_registry_writes_atomically(tmp_path) -> None:
    path = tmp_path / "workspaces.json"
    registry = WorkspaceRegistry(
        schema_version=1,
        updated_at="2026-04-26T00:00:00+00:00",
        workspaces={
            "proj-a": WorkspaceRecord(
                id="proj-a",
                label="Project A",
                ks_root="/tmp/ks",
                created_at="2026-04-26T00:00:00+00:00",
                updated_at="2026-04-26T00:00:00+00:00",
            )
        },
    )

    save_registry(registry, path)
    reloaded = load_registry(path)

    assert reloaded.workspaces["proj-a"].label == "Project A"
    assert not path.with_suffix(".json.tmp").exists()


def test_workspace_registry_rejects_corrupt_file(tmp_path) -> None:
    path = tmp_path / "workspaces.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(KSError):
        load_registry(path)

