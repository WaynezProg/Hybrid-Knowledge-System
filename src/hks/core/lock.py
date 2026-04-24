"""File lock helpers for single-process Phase 1 ingest."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from hks.errors import ExitCode, KSError


def acquire_lock(path: Path) -> TextIO:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise KSError(
            "另一個 ingest 流程正在執行",
            exit_code=ExitCode.GENERAL,
            code="LOCKED",
            details=[f"lock path: {path}"],
        ) from exc
    return handle


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    handle = acquire_lock(path)
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
