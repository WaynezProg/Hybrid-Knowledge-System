"""Deterministic watch plan generation."""

from __future__ import annotations

from hks.core.manifest import utc_now_iso
from hks.watch.models import (
    RefreshAction,
    RefreshPlan,
    WatchIssue,
    WatchRequest,
    WatchSource,
    stable_hash,
)


def build_plan(
    *,
    request: WatchRequest,
    sources: list[WatchSource],
    source_counts: dict[str, int],
    artifact_counts: dict[str, int],
    issues: list[WatchIssue],
) -> RefreshPlan:
    actions: list[RefreshAction] = []
    for source in sources:
        if source.state in {"stale", "new"}:
            actions.append(
                RefreshAction(
                    action_id=f"ingest:{source.relpath}",
                    kind="ingest",
                    source_relpath=source.relpath,
                    input_fingerprint=source.current_sha256,
                )
            )
        elif source.state == "missing" and request.prune:
            actions.append(
                RefreshAction(
                    action_id=f"prune:{source.relpath}",
                    kind="prune",
                    source_relpath=source.relpath,
                    input_fingerprint=source.manifest_sha256,
                )
            )
        elif source.state in {"unsupported", "corrupt"}:
            actions.append(
                RefreshAction(
                    action_id=f"issue:{source.relpath}",
                    kind="report_issue",
                    source_relpath=source.relpath,
                    status="skipped",
                    input_fingerprint=source.current_sha256,
                )
            )

    if request.include_graphify or request.profile in {"derived-refresh", "full"}:
        if actions or artifact_counts.get("graphify_stale", 0):
            actions.append(
                RefreshAction(
                    action_id="graphify:build",
                    kind="graphify_build",
                    source_relpath=None,
                    depends_on=[
                        action.action_id
                        for action in actions
                        if action.kind in {"ingest", "prune"}
                    ],
                )
            )

    created_at = utc_now_iso()
    fingerprint_payload = {
        "mode": request.mode,
        "profile": request.profile,
        "sources": [source.observation() for source in sources],
        "artifact_counts": artifact_counts,
        "actions": [action.to_dict() for action in actions],
        "issues": [issue.to_dict() for issue in issues],
    }
    fingerprint = stable_hash(fingerprint_payload)
    return RefreshPlan(
        plan_id=f"plan-{fingerprint[:24]}",
        created_at=created_at,
        plan_fingerprint=fingerprint,
        mode=request.mode,
        profile=request.profile,
        source_counts=source_counts,
        artifact_counts=artifact_counts,
        actions=actions,
        issues=issues,
    )


def action_counts(actions: list[RefreshAction]) -> dict[str, int]:
    counts = {"planned": 0, "skipped": 0, "running": 0, "completed": 0, "failed": 0}
    for action in actions:
        counts[action.status] += 1
    return counts
