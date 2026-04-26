"""Persistence and locking for watch artifacts."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import (
    validate_watch_latest,
    validate_watch_plan,
    validate_watch_run,
)
from hks.core.manifest import atomic_write, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError
from hks.watch.models import RefreshPlan, WatchRun


def watch_dir(paths: RuntimePaths | None = None) -> Path:
    return (paths or runtime_paths()).root / "watch"


def plans_dir(paths: RuntimePaths | None = None) -> Path:
    return watch_dir(paths) / "plans"


def runs_dir(paths: RuntimePaths | None = None) -> Path:
    return watch_dir(paths) / "runs"


def latest_path(paths: RuntimePaths | None = None) -> Path:
    return watch_dir(paths) / "latest.json"


def config_path(paths: RuntimePaths | None = None) -> Path:
    return watch_dir(paths) / "config.json"


def events_path(paths: RuntimePaths | None = None) -> Path:
    return watch_dir(paths) / "events.jsonl"


def lock_path(paths: RuntimePaths | None = None) -> Path:
    return watch_dir(paths) / ".lock"


def plan_path(plan_id: str, paths: RuntimePaths | None = None) -> Path:
    return plans_dir(paths) / f"{plan_id}.json"


def run_path(run_id: str, paths: RuntimePaths | None = None) -> Path:
    return runs_dir(paths) / f"{run_id}.json"


def save_plan(plan: RefreshPlan, *, paths: RuntimePaths | None = None) -> Path:
    resolved = paths or runtime_paths()
    payload = plan.to_dict()
    validate_watch_plan(payload)
    target = plan_path(plan.plan_id, resolved)
    atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2))
    _write_latest(
        resolved,
        latest_plan_id=plan.plan_id,
        latest_run_id=None,
        plan_fingerprint=plan.plan_fingerprint,
    )
    append_event("plan_saved", {"plan_id": plan.plan_id}, paths=resolved)
    return target


def save_run(run: WatchRun, *, paths: RuntimePaths | None = None) -> Path:
    resolved = paths or runtime_paths()
    payload = run.to_dict()
    validate_watch_run(payload)
    target = run_path(run.run_id, resolved)
    atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2))
    _write_latest(
        resolved,
        latest_plan_id=run.plan_id,
        latest_run_id=run.run_id,
        plan_fingerprint=run.plan_fingerprint,
    )
    append_event("run_saved", {"run_id": run.run_id, "status": run.status}, paths=resolved)
    return target


def load_plan(plan_id: str, *, paths: RuntimePaths | None = None) -> RefreshPlan:
    payload = cast(
        dict[str, Any],
        json.loads(plan_path(plan_id, paths).read_text(encoding="utf-8")),
    )
    validate_watch_plan(payload)
    return RefreshPlan.from_dict(payload)


def load_run(run_id: str, *, paths: RuntimePaths | None = None) -> WatchRun:
    payload = cast(
        dict[str, Any],
        json.loads(run_path(run_id, paths).read_text(encoding="utf-8")),
    )
    validate_watch_run(payload)
    return WatchRun.from_dict(payload)


def load_latest(*, paths: RuntimePaths | None = None) -> dict[str, Any] | None:
    target = latest_path(paths)
    if not target.exists():
        return None
    payload = cast(dict[str, Any], json.loads(target.read_text(encoding="utf-8")))
    validate_watch_latest(payload)
    return payload


def load_saved_source_roots(*, paths: RuntimePaths | None = None) -> list[Path]:
    target = config_path(paths)
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    roots = payload.get("source_roots", [])
    if not isinstance(roots, list):
        return []
    return [Path(str(root)).expanduser().resolve(strict=False) for root in roots]


def save_source_roots(source_roots: list[Path], *, paths: RuntimePaths | None = None) -> None:
    if not source_roots:
        return
    resolved = paths or runtime_paths()
    payload = {
        "schema_version": "1.0",
        "source_roots": [
            root.expanduser().resolve(strict=False).as_posix() for root in source_roots
        ],
        "updated_at": utc_now_iso(),
    }
    atomic_write(config_path(resolved), json.dumps(payload, ensure_ascii=False, indent=2))


def append_event(event: str, payload: dict[str, Any], *, paths: RuntimePaths | None = None) -> None:
    resolved = paths or runtime_paths()
    target = events_path(resolved)
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"timestamp": utc_now_iso(), "event": event, "payload": payload}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_latest(
    paths: RuntimePaths,
    *,
    latest_plan_id: str | None,
    latest_run_id: str | None,
    plan_fingerprint: str | None,
) -> None:
    existing = load_latest(paths=paths) or {}
    payload = {
        "schema_version": "1.0",
        "latest_plan_id": latest_plan_id or existing.get("latest_plan_id"),
        "latest_run_id": latest_run_id or existing.get("latest_run_id"),
        "updated_at": utc_now_iso(),
        "plan_fingerprint": plan_fingerprint or existing.get("plan_fingerprint"),
    }
    validate_watch_latest(payload)
    atomic_write(latest_path(paths), json.dumps(payload, ensure_ascii=False, indent=2))


@contextmanager
def watch_lock(paths: RuntimePaths | None = None) -> Iterator[None]:
    resolved = paths or runtime_paths()
    target = lock_path(resolved)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = target.open("w", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise KSError(
                "另一個 watch run 正在執行",
                exit_code=ExitCode.GENERAL,
                code="WATCH_LOCKED",
                details=[target.as_posix()],
            ) from exc
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
