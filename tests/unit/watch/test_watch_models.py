from __future__ import annotations

from hks.watch.models import RefreshAction, WatchSummaryDetail, stable_hash


def test_stable_hash_is_order_stable_for_dicts() -> None:
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})


def test_refresh_action_round_trips() -> None:
    action = RefreshAction(action_id="ingest:a.md", kind="ingest", source_relpath="a.md")

    assert RefreshAction.from_dict(action.to_dict()) == action


def test_watch_summary_detail_serializes_kind() -> None:
    detail = WatchSummaryDetail(
        operation="status",
        mode="dry-run",
        profile="scan-only",
        source_counts={
            "unchanged": 0,
            "stale": 0,
            "new": 0,
            "missing": 0,
            "unsupported": 0,
            "corrupt": 0,
        },
        action_counts={"planned": 0, "skipped": 0, "running": 0, "completed": 0, "failed": 0},
        artifacts={"plan": None, "run": None, "latest": None},
        confidence=0.0,
    )

    assert detail.to_dict()["kind"] == "watch_summary"
