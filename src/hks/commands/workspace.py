"""CLI command wrappers for workspace registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hks.adapters.contracts import validate_catalog_summary
from hks.catalog.service import summary_answer
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.workspace import service


def _response(detail: dict[str, object]) -> QueryResponse:
    validate_catalog_summary(detail)
    return QueryResponse(
        answer=summary_answer(detail),
        source=[],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="catalog_summary", detail=detail)]),
    )


def run_list(*, registry_path: Path | str | None = None) -> QueryResponse:
    return _response(service.list_workspaces(registry_path_value=registry_path).to_dict())


def run_show(workspace_id: str, *, registry_path: Path | str | None = None) -> QueryResponse:
    return _response(
        service.show_workspace(workspace_id, registry_path_value=registry_path).to_dict()
    )


def run_register(
    workspace_id: str,
    ks_root: Path | str,
    *,
    label: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
    registry_path: Path | str | None = None,
) -> QueryResponse:
    return _response(
        service.register_workspace(
            workspace_id,
            ks_root=ks_root,
            label=label,
            tags=tags,
            metadata=metadata,
            force=force,
            registry_path_value=registry_path,
        ).to_dict()
    )


def run_remove(workspace_id: str, *, registry_path: Path | str | None = None) -> QueryResponse:
    return _response(
        service.remove_workspace(workspace_id, registry_path_value=registry_path).to_dict()
    )


def run_use(workspace_id: str, *, registry_path: Path | str | None = None) -> QueryResponse:
    return _response(
        service.use_workspace(workspace_id, registry_path_value=registry_path).to_dict()
    )


def run_query(
    workspace_id: str,
    question: str,
    *,
    writeback: str = "no",
    registry_path: Path | str | None = None,
    ks_root: Path | str | None = None,
) -> QueryResponse:
    return service.query_workspace(
        workspace_id,
        question,
        writeback=writeback,
        registry_path_value=registry_path,
        ks_root=ks_root,
    )
