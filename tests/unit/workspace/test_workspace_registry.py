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


def test_concurrent_workspace_registrations_all_survive(tmp_path, monkeypatch) -> None:
    import threading
    import time

    from hks.workspace import service

    registry_file = tmp_path / "config" / "workspaces.json"
    real_load = service.load_registry

    def slow_load(path=None):
        registry = real_load(path)
        time.sleep(0.02)  # widen the read-modify-write window
        return registry

    monkeypatch.setattr(service, "load_registry", slow_load)
    ids = [f"proj-{index}" for index in range(12)]
    errors: list[BaseException] = []

    def register(workspace_id: str) -> None:
        try:
            service.register_workspace(
                workspace_id,
                ks_root=tmp_path / "roots" / workspace_id,
                registry_path_value=registry_file,
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=register, args=(workspace_id,)) for workspace_id in ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(load_registry(registry_file).workspaces) == sorted(ids)

    removers = [
        threading.Thread(
            target=service.remove_workspace,
            args=(workspace_id,),
            kwargs={"registry_path_value": registry_file},
        )
        for workspace_id in ids[:6]
    ]
    for thread in removers:
        thread.start()
    for thread in removers:
        thread.join()

    assert sorted(load_registry(registry_file).workspaces) == sorted(ids[6:])
    assert (registry_file.parent / "workspaces.json.lock").exists()
