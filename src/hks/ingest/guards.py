"""Size and time guards for ingest-time parsers.

- `preflight_size_check(path, max_mb)` raises `OversizeError` if the file
  exceeds the configured limit; the pipeline maps this to DATAERR.
- `with_timeout(seconds)` bounds the wall time of its body. On the main
  thread it uses `SIGALRM` (unchanged CLI behaviour); off the main thread
  (MCP / HTTP adapters run core work in worker threads) it uses a timer that
  injects `TimeoutError` into the calling thread. Not reentrant.
"""

from __future__ import annotations

import ctypes
import signal
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from hks.core.config import config_value


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


@dataclass(frozen=True, slots=True)
class ImageLimits:
    timeout_seconds: int
    max_file_mb: int
    max_pixels: int


_DEFAULT_TIMEOUT_SEC = 60
_DEFAULT_MAX_FILE_MB = 200
_DEFAULT_IMAGE_TIMEOUT_SEC = 30
_DEFAULT_IMAGE_MAX_FILE_MB = 20
_DEFAULT_IMAGE_MAX_PIXELS = 100_000_000
_TIMEOUT_MIN, _TIMEOUT_MAX = 5, 600
_SIZE_MIN, _SIZE_MAX = 1, 2048
_PIXELS_MIN, _PIXELS_MAX = 1, 500_000_000


def _read_int_env(
    name: str,
    default: int,
    lo: int,
    hi: int,
) -> int:
    raw = config_value(name)
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


def load_image_limits() -> ImageLimits:
    """Read image-specific limits from env with validation."""

    return ImageLimits(
        timeout_seconds=_read_int_env(
            "HKS_IMAGE_TIMEOUT_SEC", _DEFAULT_IMAGE_TIMEOUT_SEC, _TIMEOUT_MIN, _TIMEOUT_MAX
        ),
        max_file_mb=_read_int_env(
            "HKS_IMAGE_MAX_FILE_MB", _DEFAULT_IMAGE_MAX_FILE_MB, _SIZE_MIN, _SIZE_MAX
        ),
        max_pixels=_read_int_env(
            "HKS_IMAGE_MAX_PIXELS", _DEFAULT_IMAGE_MAX_PIXELS, _PIXELS_MIN, _PIXELS_MAX
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
def _sigalrm_timeout(seconds: int) -> Iterator[None]:
    previous = signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _set_async_exc(thread_id: int, exc: type[BaseException] | None) -> None:
    # CPython API: schedule (or, with NULL, clear) an exception to be raised in
    # another thread the next time it executes Python bytecode.
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc) if exc is not None else None,
    )


@contextmanager
def _thread_timeout(seconds: int) -> Iterator[None]:
    """Timeout for non-main threads, where `signal.signal` is unavailable.

    A `threading.Timer` raises `TimeoutError` inside the calling thread via
    `PyThreadState_SetAsyncExc`. Like SIGALRM, delivery happens between Python
    bytecodes, so the body is interrupted in place (no leaked worker thread);
    unlike SIGALRM it cannot interrupt a single long blocking C call, which
    sees the exception right after that call returns.
    """

    thread_id = threading.get_ident()
    state_lock = threading.Lock()
    state = {"active": True, "fired": False}

    def _fire() -> None:
        with state_lock:
            if not state["active"]:
                return
            state["fired"] = True
            _set_async_exc(thread_id, TimeoutError)

    timer = threading.Timer(float(seconds), _fire)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        with state_lock:
            state["active"] = False
            if state["fired"]:
                # Body finished before the injected exception was delivered:
                # clear it so it cannot surface outside the guarded block.
                _set_async_exc(thread_id, None)


@contextmanager
def with_timeout(seconds: int) -> Iterator[None]:
    """Bound the wall time of the body; raise `TimeoutError` when exceeded.

    - `seconds <= 0` disables the timer (acts as a no-op).
    - Main thread: SIGALRM, restoring the prior handler on exit.
    - Other threads: async-exception timer (see `_thread_timeout`).
    - Not reentrant.
    """

    if seconds <= 0:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        with _thread_timeout(seconds):
            yield
        return
    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - POSIX only
        with _thread_timeout(seconds):
            yield
        return
    with _sigalrm_timeout(seconds):
        yield
