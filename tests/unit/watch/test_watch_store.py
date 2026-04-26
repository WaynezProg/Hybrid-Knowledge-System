from __future__ import annotations

from hks.core.paths import runtime_paths
from hks.watch.models import (
    RefreshPlan,
    WatchRequest,
    WatchSummaryDetail,
    zero_artifact_counts,
    zero_source_counts,
)
from hks.watch.planner import build_plan
from hks.watch.store import load_latest, save_plan


def test_watch_store_writes_plan_and_latest(tmp_ks_root) -> None:
    paths = runtime_paths(tmp_ks_root)
    plan: RefreshPlan = build_plan(
        request=WatchRequest(operation="scan"),
        sources=[],
        source_counts=zero_source_counts(),
        artifact_counts=zero_artifact_counts(),
        issues=[],
    )

    target = save_plan(plan, paths=paths)

    assert target.exists()
    assert load_latest(paths=paths)["latest_plan_id"] == plan.plan_id


def test_watch_summary_status_artifacts_shape() -> None:
    detail = WatchSummaryDetail(
        operation="status",
        mode="dry-run",
        profile="scan-only",
        source_counts=zero_source_counts(),
        action_counts={"planned": 0, "skipped": 0, "running": 0, "completed": 0, "failed": 0},
        artifacts={"plan": None, "run": None, "latest": None},
    )

    assert set(detail.to_dict()["artifacts"]) == {"plan", "run", "latest"}
