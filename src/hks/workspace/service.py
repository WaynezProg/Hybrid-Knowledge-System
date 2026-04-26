"""Workspace registry and workspace-scoped query service."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from hks.catalog.models import CatalogSummaryDetail
from hks.commands import query as query_command
from hks.core.manifest import load_manifest, utc_now_iso
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse
from hks.errors import ExitCode, KSError
from hks.workspace.models import WorkspaceRecord, WorkspaceRegistry, WorkspaceStatus
from hks.workspace.registry import load_registry, registry_path, save_registry
from hks.workspace.validation import (
    resolve_workspace_root,
    shell_export_command,
    validate_metadata,
    validate_workspace_id,
)


@contextmanager
def scoped_ks_root(ks_root: str) -> Iterator[None]:
    previous = os.environ.get("KS_ROOT")
    os.environ["KS_ROOT"] = str(Path(ks_root).expanduser().resolve(strict=False))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("KS_ROOT", None)
        else:
            os.environ["KS_ROOT"] = previous


def _workspace_status(record: WorkspaceRecord, *, duplicate: bool = False) -> WorkspaceStatus:
    root = Path(record.ks_root)
    if not root.exists():
        return WorkspaceStatus(
            id=record.id,
            label=record.label,
            ks_root=record.ks_root,
            status="missing",
            source_count=0,
            formats={},
            last_ingested_at=None,
            issues=["workspace root does not exist"],
        )
    paths = runtime_paths(root)
    if not paths.manifest.exists():
        return WorkspaceStatus(
            id=record.id,
            label=record.label,
            ks_root=record.ks_root,
            status="uninitialized",
            source_count=0,
            formats={},
            last_ingested_at=None,
            issues=["manifest.json is missing"],
        )
    try:
        manifest = load_manifest(paths.manifest)
    except Exception as exc:
        return WorkspaceStatus(
            id=record.id,
            label=record.label,
            ks_root=record.ks_root,
            status="corrupt",
            source_count=0,
            formats={},
            last_ingested_at=None,
            issues=[f"manifest cannot be parsed: {exc}"],
        )
    formats = Counter(entry.format for entry in manifest.entries.values())
    last_ingested = max((entry.ingested_at for entry in manifest.entries.values()), default=None)
    issues = ["another workspace points to the same root"] if duplicate else []
    return WorkspaceStatus(
        id=record.id,
        label=record.label,
        ks_root=record.ks_root,
        status="duplicate_root" if duplicate else "ready",
        source_count=len(manifest.entries),
        formats=dict(sorted(formats.items())),
        last_ingested_at=last_ingested,
        issues=issues,
    )


def _duplicate_ids(registry: WorkspaceRegistry) -> set[str]:
    by_root: dict[str, list[str]] = defaultdict(list)
    for record in registry.workspaces.values():
        by_root[record.ks_root].append(record.id)
    return {
        workspace_id
        for ids in by_root.values()
        if len(ids) > 1
        for workspace_id in ids
    }


def list_workspaces(*, registry_path_value: str | Path | None = None) -> CatalogSummaryDetail:
    registry = load_registry(registry_path_value)
    duplicates = _duplicate_ids(registry)
    statuses = [
        _workspace_status(record, duplicate=record.id in duplicates).to_dict()
        for record in sorted(registry.workspaces.values(), key=lambda item: item.id)
    ]
    return CatalogSummaryDetail(
        operation="workspace.list",
        registry_path=registry_path(registry_path_value).as_posix(),
        total_count=len(statuses),
        filtered_count=len(statuses),
        filter=None,
        workspaces=statuses,
    )


def get_workspace(
    workspace_id: str,
    *,
    registry_path_value: str | Path | None = None,
) -> tuple[WorkspaceRecord, WorkspaceStatus]:
    normalized_id = validate_workspace_id(workspace_id)
    registry = load_registry(registry_path_value)
    record = registry.workspaces.get(normalized_id)
    if record is None:
        raise KSError(
            f"workspace `{normalized_id}` 不存在",
            exit_code=ExitCode.NOINPUT,
            code="WORKSPACE_NOT_FOUND",
        )
    status = _workspace_status(record, duplicate=record.id in _duplicate_ids(registry))
    return record, status


def show_workspace(
    workspace_id: str,
    *,
    registry_path_value: str | Path | None = None,
) -> CatalogSummaryDetail:
    record, status = get_workspace(workspace_id, registry_path_value=registry_path_value)
    return CatalogSummaryDetail(
        operation="workspace.show",
        workspace_id=record.id,
        ks_root=record.ks_root,
        registry_path=registry_path(registry_path_value).as_posix(),
        total_count=1,
        filtered_count=1,
        filter=None,
        workspaces=[status.to_dict()],
    )


def register_workspace(
    workspace_id: str,
    *,
    ks_root: str | Path,
    label: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
    registry_path_value: str | Path | None = None,
) -> CatalogSummaryDetail:
    normalized_id = validate_workspace_id(workspace_id)
    root = resolve_workspace_root(ks_root)
    registry = load_registry(registry_path_value)
    now = utc_now_iso()
    existing = registry.workspaces.get(normalized_id)
    previous_root = existing.ks_root if existing else None
    if existing is not None and existing.ks_root != root.as_posix() and not force:
        raise KSError(
            f"workspace `{normalized_id}` already points to another KS_ROOT",
            exit_code=ExitCode.NOINPUT,
            code="WORKSPACE_CONFLICT",
            details=[f"existing: {existing.ks_root}", f"requested: {root.as_posix()}"],
            hint="rerun with --force to replace the registered root",
        )
    registry.workspaces[normalized_id] = WorkspaceRecord(
        id=normalized_id,
        label=label or (existing.label if existing else normalized_id),
        ks_root=root.as_posix(),
        created_at=existing.created_at if existing else now,
        updated_at=now,
        tags=sorted(set(tags or (existing.tags if existing else []))),
        metadata=validate_metadata(
            metadata if metadata is not None else (existing.metadata if existing else {})
        ),
    )
    path = save_registry(registry, registry_path_value)
    status = _workspace_status(registry.workspaces[normalized_id], duplicate=False)
    return CatalogSummaryDetail(
        operation="workspace.register",
        workspace_id=normalized_id,
        ks_root=root.as_posix(),
        registry_path=path.as_posix(),
        previous_root=previous_root if force else None,
        total_count=1,
        filtered_count=1,
        filter=None,
        workspaces=[status.to_dict()],
    )


def remove_workspace(
    workspace_id: str,
    *,
    registry_path_value: str | Path | None = None,
) -> CatalogSummaryDetail:
    normalized_id = validate_workspace_id(workspace_id)
    registry = load_registry(registry_path_value)
    record = registry.workspaces.pop(normalized_id, None)
    if record is None:
        raise KSError(
            f"workspace `{normalized_id}` 不存在",
            exit_code=ExitCode.NOINPUT,
            code="WORKSPACE_NOT_FOUND",
        )
    path = save_registry(registry, registry_path_value)
    return CatalogSummaryDetail(
        operation="workspace.remove",
        workspace_id=normalized_id,
        ks_root=record.ks_root,
        registry_path=path.as_posix(),
        total_count=0,
        filtered_count=0,
        filter=None,
    )


def use_workspace(
    workspace_id: str,
    *,
    registry_path_value: str | Path | None = None,
) -> CatalogSummaryDetail:
    record, status = get_workspace(workspace_id, registry_path_value=registry_path_value)
    if status.status != "ready" and status.status != "duplicate_root":
        raise KSError(
            f"workspace `{record.id}` 尚未 ready",
            exit_code=ExitCode.NOINPUT,
            code="WORKSPACE_NOT_READY",
            details=status.issues,
        )
    return CatalogSummaryDetail(
        operation="workspace.use",
        workspace_id=record.id,
        ks_root=record.ks_root,
        registry_path=registry_path(registry_path_value).as_posix(),
        total_count=1,
        filtered_count=1,
        filter=None,
        workspaces=[status.to_dict()],
        export_command=shell_export_command(record.ks_root),
    )


def query_workspace(
    workspace_id: str,
    question: str,
    *,
    writeback: str = "no",
    registry_path_value: str | Path | None = None,
    ks_root: str | Path | None = None,
) -> QueryResponse:
    record, status = get_workspace(workspace_id, registry_path_value=registry_path_value)
    if ks_root is not None:
        explicit = resolve_workspace_root(ks_root).as_posix()
        if explicit != record.ks_root:
            raise KSError(
                "workspace id and explicit ks_root point to different runtimes",
                exit_code=ExitCode.USAGE,
                code="USAGE",
            )
    if status.status != "ready" and status.status != "duplicate_root":
        raise KSError(
            f"workspace `{record.id}` 尚未 ready",
            exit_code=ExitCode.NOINPUT,
            code="WORKSPACE_NOT_READY",
            details=status.issues,
        )
    with scoped_ks_root(record.ks_root):
        return query_command.run(question, writeback=writeback)
