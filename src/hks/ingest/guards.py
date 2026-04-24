"""Size and time guards for Office ingest (spec FR-063 / FR-064).

- `preflight_size_check(path, max_mb)` raises `OversizeError` if the file
  exceeds the configured limit; the pipeline maps this to DATAERR.
- `with_timeout(seconds)` is a POSIX-only context manager based on
  `SIGALRM`; the running thread must be the main thread. Nested usage is
  rejected (we keep the itimer semantics simple).
"""

from __future__ import annotations

import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class OversizeError(Exception):
    """Raised when a file exceeds the configured size limit."""

    def __init__(self, path: Path, size_mb: float, limit_mb: int) -> None:
        super().__init__(
            f"file too large ({size_mb:.1f}MB > {limit_mb}MB): {path}",
        )
        self.path = path
        self.size_mb = size_mb
        self.limit_mb = limit_mb


@dataclass(frozen=True, slots=True)
class OfficeLimits:
    timeout_seconds: int
    max_file_mb: int


_DEFAULT_TIMEOUT_SEC = 60
_DEFAULT_MAX_FILE_MB = 200
_TIMEOUT_MIN, _TIMEOUT_MAX = 5, 600
_SIZE_MIN, _SIZE_MAX = 1, 2048


def _read_int_env(
    name: str,
    default: int,
    lo: int,
    hi: int,
) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an integer in [{lo}, {hi}], got {raw!r}",
        ) from exc
    if not lo <= value <= hi:
        raise ValueError(
            f"{name} must be in [{lo}, {hi}], got {value}",
        )
    return value


def load_office_limits() -> OfficeLimits:
    """Read Office-specific limits from env with validation.

    Raises `ValueError` with a user-facing message if env values are
    malformed; callers should translate to CLI USAGE exit.
    """

    return OfficeLimits(
        timeout_seconds=_read_int_env(
            "HKS_OFFICE_TIMEOUT_SEC", _DEFAULT_TIMEOUT_SEC, _TIMEOUT_MIN, _TIMEOUT_MAX
        ),
        max_file_mb=_read_int_env(
            "HKS_OFFICE_MAX_FILE_MB", _DEFAULT_MAX_FILE_MB, _SIZE_MIN, _SIZE_MAX
        ),
    )


def preflight_size_check(path: Path, max_mb: int) -> None:
    """Raise OversizeError if `path` exceeds `max_mb`."""

    size_bytes = path.stat().st_size
    limit_bytes = max_mb * 1024 * 1024
    if size_bytes > limit_bytes:
        raise OversizeError(path, size_bytes / (1024 * 1024), max_mb)


def _raise_timeout(signum: int, frame: object) -> None:  # pragma: no cover - signal handler
    raise TimeoutError("office parser timed out")


@contextmanager
def with_timeout(seconds: int) -> Iterator[None]:
    """POSIX-only timeout context manager using SIGALRM.

    - `seconds <= 0` disables the timer (acts as a no-op).
    - Restores the prior SIGALRM handler on exit.
    - Not reentrant.
    """

    if seconds <= 0:
        yield
        return
    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - POSIX only
        yield
        return
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
