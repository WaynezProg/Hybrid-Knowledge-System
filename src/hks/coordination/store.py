"""Filesystem-backed coordination ledger."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO, cast

import jsonschema

from hks.adapters.contracts import load_coordination_ledger_schema
from hks.coordination.models import CoordinationState
from hks.core.manifest import atomic_write, utc_now_iso
from hks.core.paths import RuntimePaths, runtime_paths
from hks.errors import ExitCode, KSError


class CoordinationStore:
    """Read and mutate `/ks/coordination` with a single file lock."""

    def __init__(self, paths: RuntimePaths | None = None) -> None:
        self.paths = paths or runtime_paths()
        self.dir = self.paths.root / "coordination"
        self.state_path = self.dir / "state.json"
        self.events_path = self.dir / "events.jsonl"
        self.lock_path = self.dir / ".lock"

    def assert_runtime_ready(self) -> None:
        missing = [
            path
            for path in (self.paths.manifest, self.paths.wiki, self.paths.vector_db)
            if not path.exists()
        ]
        if missing:
            raise KSError(
                "/ks 尚未初始化，coordination 需要已建立的 runtime",
                exit_code=ExitCode.NOINPUT,
                code="NOINPUT",
                details=[f"missing: {path}" for path in missing],
                hint="run `ks ingest <path>` first",
            )

    @contextmanager
    def locked(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle: TextIO = self.lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        except BlockingIOError as error:
            raise KSError(
                "另一個 coordination 流程正在執行",
                exit_code=ExitCode.GENERAL,
                code="LOCKED",
                details=[f"lock path: {self.lock_path}"],
            ) from error
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def empty_state(self) -> CoordinationState:
        return CoordinationState(schema_version=1, updated_at=utc_now_iso())

    def load(self) -> CoordinationState:
        self.assert_runtime_ready()
        if not self.state_path.exists():
            return self.empty_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=payload, schema=load_coordination_ledger_schema())
            return CoordinationState.from_dict(cast(dict[str, Any], payload))
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            jsonschema.ValidationError,
        ) as error:
            raise KSError(
                "coordination ledger 無法讀取",
                exit_code=ExitCode.DATAERR,
                code="LEDGER_DATAERR",
                details=[str(error)],
            ) from error

    def save(self, state: CoordinationState) -> None:
        self.assert_runtime_ready()
        state.updated_at = utc_now_iso()
        payload = state.to_dict()
        try:
            jsonschema.validate(instance=payload, schema=load_coordination_ledger_schema())
        except jsonschema.ValidationError as error:
            raise KSError(
                "coordination ledger schema 驗證失敗",
                exit_code=ExitCode.DATAERR,
                code="LEDGER_DATAERR",
                details=[str(error)],
            ) from error
        atomic_write(self.state_path, json.dumps(payload, ensure_ascii=False, indent=2))

    def append_events(self, events: Sequence[Mapping[str, Any]]) -> None:
        if not events:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
                handle.write("\n")

    def reset_unsafe(self) -> None:
        """Test helper for removing coordination artifacts under the current KS_ROOT."""

        for path in (self.state_path, self.events_path, self.lock_path):
            if path.exists():
                path.unlink()


def coordination_dir(root: Path | str | None = None) -> Path:
    return runtime_paths(root).root / "coordination"
