from __future__ import annotations

from hks.workspace.models import WorkspaceRecord, WorkspaceRegistry


def test_workspace_registry_round_trips_records() -> None:
    record = WorkspaceRecord(
        id="proj-a",
        label="Project A",
        ks_root="/tmp/ks",
        created_at="2026-04-26T00:00:00+00:00",
        updated_at="2026-04-26T00:00:00+00:00",
    )
    registry = WorkspaceRegistry(
        schema_version=1,
        updated_at="2026-04-26T00:00:00+00:00",
        workspaces={"proj-a": record},
    )

    reloaded = WorkspaceRegistry.from_dict(registry.to_dict())

    assert reloaded.workspaces["proj-a"].ks_root == "/tmp/ks"

