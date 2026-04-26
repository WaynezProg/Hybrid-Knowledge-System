"""Bounded watch action executor."""

from __future__ import annotations

from pathlib import Path

from hks.commands import graphify as graphify_command
from hks.commands import ingest as ingest_command
from hks.core.paths import RuntimePaths
from hks.errors import ExitCode, KSError
from hks.watch.models import RefreshAction, WatchRequest, WatchSource


def execute_actions(
    *,
    request: WatchRequest,
    actions: list[RefreshAction],
    sources: list[WatchSource],
    paths: RuntimePaths,
) -> list[RefreshAction]:
    if request.mode != "execute":
        return actions
    if request.profile == "scan-only":
        return [action.with_status("skipped") for action in actions]

    executed: list[RefreshAction] = []
    source_roots = sorted(
        {
            Path(source.root_path)
            for source in sources
            if source.root_path and source.state in {"stale", "new"}
        }
    )
    ingest_outputs: list[str] = []
    try:
        if any(action.kind == "ingest" for action in actions):
            for root in source_roots:
                response = ingest_command.run(root, prune=request.prune)
                detail = response.trace.steps[0].detail
                ingest_outputs.extend(detail.get("created", []))
                ingest_outputs.extend(detail.get("updated", []))
        for action in actions:
            if action.kind == "ingest":
                output_ref = action.source_relpath or ""
                executed.append(action.with_status("completed", output_refs=[output_ref]))
            elif action.kind == "graphify_build":
                response = graphify_command.run_build(
                    mode="store",
                    requested_by=request.requested_by,
                )
                detail = response.trace.steps[0].detail
                output_refs = [
                    value
                    for value in detail.get("artifacts", {}).values()
                    if isinstance(value, str)
                ]
                executed.append(action.with_status("completed", output_refs=output_refs))
            elif action.kind == "report_issue":
                executed.append(action.with_status("skipped"))
            else:
                executed.append(action.with_status("skipped"))
    except KSError as exc:
        failed = _mark_failed(actions, executed, exc)
        if failed:
            return failed
        raise
    except Exception as exc:
        error = KSError(str(exc), exit_code=ExitCode.GENERAL, code=type(exc).__name__.upper())
        failed = _mark_failed(actions, executed, error)
        if failed:
            return failed
        raise
    _ = paths
    _ = ingest_outputs
    return executed


def _mark_failed(
    actions: list[RefreshAction],
    executed: list[RefreshAction],
    error: KSError,
) -> list[RefreshAction]:
    executed_ids = {action.action_id for action in executed}
    failure_payload = {
        "code": error.code,
        "exit_code": int(error.exit_code),
        "message": error.message,
    }
    marked: list[RefreshAction] = list(executed)
    failed_once = False
    for action in actions:
        if action.action_id in executed_ids:
            continue
        if not failed_once:
            marked.append(action.with_status("failed", error=failure_payload))
            failed_once = True
        else:
            marked.append(action.with_status("skipped"))
    return marked
