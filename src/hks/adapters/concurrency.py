"""Run synchronous HKS core calls off the adapter event loop.

FastMCP calls sync tools directly on the event loop, and Starlette handlers
are async, so a long ``hks_ingest`` / ``hks_graphify_build`` used to freeze
pings, ``tools/list`` and cancellation. Adapters now await
``run_core(fn, ...)``, which executes ``fn`` in a worker thread.

Core work is serialized by one process-wide lock. Before this change the
event loop already executed one core call at a time; keeping that guarantee
means moving to threads does not introduce new races (non-blocking ingest
``file_lock`` returning ``LOCKED`` to a concurrent caller, in-process caches,
readers observing a half-finished ingest). Only the event loop gains
concurrency, not the core.

Cancellation abandons the worker thread: the caller returns immediately, a
call still waiting for the lock is skipped, and a call already running
finishes in the background (worker threads are non-daemon, so interpreter
shutdown still waits for it instead of cutting a write in half).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import anyio
import anyio.to_thread

_CORE_LOCK = threading.Lock()


async def run_core[T](fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    cancelled = threading.Event()

    def _invoke() -> T | None:
        with _CORE_LOCK:
            if cancelled.is_set():
                return None
            return fn(*args, **kwargs)

    try:
        result = await anyio.to_thread.run_sync(_invoke, abandon_on_cancel=True)
    except anyio.get_cancelled_exc_class():
        cancelled.set()
        raise
    return result  # type: ignore[return-value]
