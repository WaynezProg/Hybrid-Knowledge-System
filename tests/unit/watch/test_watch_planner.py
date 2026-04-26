from __future__ import annotations

from hks.watch.models import WatchRequest, WatchSource, zero_artifact_counts, zero_source_counts
from hks.watch.planner import build_plan


def test_watch_plan_fingerprint_stable_for_same_inputs() -> None:
    request = WatchRequest(operation="scan")
    source = WatchSource(relpath="a.md", state="stale", current_sha256="sha")
    source_counts = zero_source_counts()
    source_counts["stale"] = 1

    first = build_plan(
        request=request,
        sources=[source],
        source_counts=source_counts,
        artifact_counts=zero_artifact_counts(),
        issues=[],
    )
    second = build_plan(
        request=request,
        sources=[source],
        source_counts=source_counts,
        artifact_counts=zero_artifact_counts(),
        issues=[],
    )

    assert first.plan_fingerprint == second.plan_fingerprint
    assert first.actions[0].kind == "ingest"
