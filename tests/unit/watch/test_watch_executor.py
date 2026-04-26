from __future__ import annotations

from hks.core.paths import runtime_paths
from hks.watch.executor import execute_actions
from hks.watch.models import RefreshAction, WatchRequest, WatchSource


def test_executor_dry_run_leaves_actions_planned(tmp_ks_root) -> None:
    action = RefreshAction(action_id="ingest:a.md", kind="ingest", source_relpath="a.md")

    result = execute_actions(
        request=WatchRequest(operation="run", mode="dry-run"),
        actions=[action],
        sources=[WatchSource(relpath="a.md", state="stale")],
        paths=runtime_paths(tmp_ks_root),
    )

    assert result[0].status == "planned"
