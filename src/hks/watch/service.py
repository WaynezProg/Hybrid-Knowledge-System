"""Watch service orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from hks.adapters.contracts import validate_watch_summary
from hks.core.manifest import load_manifest, utc_now_iso
from hks.core.paths import runtime_paths
from hks.errors import ExitCode, KSError
from hks.watch.executor import execute_actions
from hks.watch.lineage import inspect_lineage
from hks.watch.models import (
    RefreshAction,
    RefreshPlan,
    WatchOperation,
    WatchRequest,
    WatchRun,
    WatchRunStatus,
    WatchSource,
    WatchSummaryDetail,
    zero_action_counts,
    zero_source_counts,
)
from hks.watch.planner import action_counts, build_plan
from hks.watch.scanner import scan_sources
from hks.watch.store import (
    latest_path,
    load_latest,
    load_run,
    load_saved_source_roots,
    plan_path,
    run_path,
    save_plan,
    save_run,
    save_source_roots,
    watch_lock,
)


def scan(request: WatchRequest) -> tuple[WatchSummaryDetail, RefreshPlan]:
    paths = runtime_paths()
    _assert_runtime_ready(paths.manifest)
    manifest = load_manifest(paths.manifest)
    source_roots = _resolve_source_roots(request)
    sources, source_issues, source_counts = scan_sources(
        paths=paths,
        manifest_entries=dict(manifest.entries),
        source_roots=source_roots,
    )
    artifact_counts, lineage_issues = inspect_lineage(paths=paths, sources=sources)
    plan = build_plan(
        request=request,
        sources=sources,
        source_counts=source_counts,
        artifact_counts=artifact_counts,
        issues=[*source_issues, *lineage_issues],
    )
    save_source_roots(source_roots, paths=paths)
    plan_file = save_plan(plan, paths=paths)
    summary = _summary(
        operation="scan",
        request=request,
        plan=plan,
        run_id=None,
        actions=plan.actions,
        plan_file=plan_file.as_posix(),
        run_file=None,
    )
    validate_watch_summary(summary.to_dict())
    return summary, plan


def run(request: WatchRequest) -> tuple[WatchSummaryDetail, WatchRun]:
    paths = runtime_paths()
    with watch_lock(paths):
        scan_summary, plan = scan(request)
        _ = scan_summary
        created_at = utc_now_iso()
        actions = execute_actions(
            request=request,
            actions=plan.actions,
            sources=_plan_sources(request),
            paths=paths,
        )
        completed_at = utc_now_iso()
        status = "planned" if request.mode == "dry-run" else "completed"
        if any(action.status == "failed" for action in actions):
            status = "failed"
        elif any(action.status == "planned" for action in actions) and request.mode == "execute":
            status = "partial"
        run_id = f"run-{created_at.replace(':', '').replace('+', 'z')}"
        summary = _summary(
            operation="run",
            request=request,
            plan=plan,
            run_id=run_id,
            actions=actions,
            plan_file=plan_path(plan.plan_id, paths).as_posix(),
            run_file=run_path(run_id, paths).as_posix(),
        )
        run_artifact = WatchRun(
            run_id=run_id,
            created_at=created_at,
            completed_at=completed_at,
            status=cast(WatchRunStatus, status),
            plan_id=plan.plan_id,
            plan_fingerprint=plan.plan_fingerprint,
            mode=request.mode,
            profile=request.profile,
            requested_by=request.requested_by,
            actions=actions,
            summary=summary,
        )
        save_run(run_artifact, paths=paths)
        return summary, run_artifact


def status(request: WatchRequest) -> WatchSummaryDetail:
    paths = runtime_paths()
    latest = load_latest(paths=paths)
    if latest is None:
        summary = WatchSummaryDetail(
            operation="status",
            mode=request.mode,
            profile=request.profile,
            plan_id=None,
            run_id=None,
            plan_fingerprint=None,
            source_counts=zero_source_counts(),
            action_counts=zero_action_counts(),
            artifacts={"plan": None, "run": None, "latest": None},
            confidence=0.0,
        )
        validate_watch_summary(summary.to_dict())
        return summary
    run_id = latest.get("latest_run_id")
    if isinstance(run_id, str) and run_path(run_id, paths).exists():
        run_artifact = load_run(run_id, paths=paths)
        summary = run_artifact.summary
        validate_watch_summary(summary.to_dict())
        return WatchSummaryDetail(
            operation="status",
            mode=summary.mode,
            profile=summary.profile,
            plan_id=summary.plan_id,
            run_id=summary.run_id,
            plan_fingerprint=summary.plan_fingerprint,
            source_counts=summary.source_counts,
            action_counts=summary.action_counts,
            artifacts=summary.artifacts,
            idempotent_reuse=summary.idempotent_reuse,
            confidence=summary.confidence,
        )
    summary = WatchSummaryDetail(
        operation="status",
        mode=request.mode,
        profile=request.profile,
        plan_id=latest.get("latest_plan_id"),
        run_id=None,
        plan_fingerprint=latest.get("plan_fingerprint"),
        source_counts=zero_source_counts(),
        action_counts=zero_action_counts(),
        artifacts={
            "plan": (
                plan_path(str(latest["latest_plan_id"]), paths).as_posix()
                if latest.get("latest_plan_id")
                else None
            ),
            "run": None,
            "latest": latest_path(paths).as_posix(),
        },
        confidence=1.0,
    )
    validate_watch_summary(summary.to_dict())
    return summary


def _resolve_source_roots(request: WatchRequest) -> list[Path]:
    if request.source_roots:
        return [root.expanduser().resolve(strict=False) for root in request.source_roots]
    return load_saved_source_roots()


def _plan_sources(request: WatchRequest) -> list[WatchSource]:
    resolved_paths = runtime_paths()
    manifest = load_manifest(resolved_paths.manifest)
    sources, _, _ = scan_sources(
        paths=resolved_paths,
        manifest_entries=dict(manifest.entries),
        source_roots=_resolve_source_roots(request),
    )
    return sources


def _summary(
    *,
    operation: WatchOperation,
    request: WatchRequest,
    plan: RefreshPlan,
    run_id: str | None,
    actions: list[RefreshAction],
    plan_file: str | None,
    run_file: str | None,
) -> WatchSummaryDetail:
    artifacts = {"plan": plan_file, "run": run_file, "latest": latest_path().as_posix()}
    return WatchSummaryDetail(
        operation=operation,
        mode=request.mode,
        profile=request.profile,
        plan_id=plan.plan_id,
        run_id=run_id,
        plan_fingerprint=plan.plan_fingerprint,
        source_counts=plan.source_counts,
        action_counts=action_counts(actions),
        artifacts=artifacts,
        confidence=1.0,
    )


def _assert_runtime_ready(manifest_path: Path) -> None:
    if not manifest_path.exists():
        raise KSError(
            "/ks/ 尚未初始化，請先執行 ks ingest <path>",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="run `ks ingest <path>`",
        )


def summary_answer(detail: dict[str, object]) -> str:
    operation = detail["operation"]
    counts = cast(dict[str, int], detail["source_counts"])
    action = cast(dict[str, int], detail["action_counts"])
    return (
        f"watch {operation} 完成："
        f"{counts.get('stale', 0)} stale / {counts.get('new', 0)} new / "
        f"{counts.get('missing', 0)} missing；"
        f"{action.get('completed', 0)} completed / {action.get('failed', 0)} failed"
    )


def detail_to_json(detail: WatchSummaryDetail) -> str:
    return json.dumps(detail.to_dict(), ensure_ascii=False, indent=2)
