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

``run_core_light`` is the exception to the serialization: it runs ``fn`` on a
worker thread *without* the core lock, so a lease heartbeat or a status read
is not stuck behind a long ingest. It is only for calls that meet all of:

* every read-modify-write is guarded by the call's own blocking file lock
  (coordination ledger), or the call only reads files that their writers
  replace with ``atomic_write`` (registry, manifest, watch artifacts);
* no vector / graph store, model backend, sqlite connection or other
  in-process cache is touched;
* nothing it reads is composed from several files that an ingest updates in
  separate steps (that is why source list/show stay on ``run_core``).

It is a separate function rather than a keyword on ``run_core`` because the
HTTP adapter forwards request bodies as ``**kwargs``; a keyword would let a
client opt out of the lock.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from functools import partial
from typing import Any

import anyio
import anyio.to_thread
from anyio.lowlevel import RunVar

_CORE_LOCK = threading.Lock()

# Light calls get their own thread budget: calls queued on ``_CORE_LOCK`` each
# hold a slot of anyio's default limiter while they wait, and must not be able
# to starve the calls that exist to stay responsive.
_LIGHT_THREADS = 8
_LIGHT_LIMITER: RunVar[anyio.CapacityLimiter] = RunVar("hks_light_core_limiter")


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


def _light_limiter() -> anyio.CapacityLimiter:
    try:
        return _LIGHT_LIMITER.get()
    except LookupError:
        limiter = anyio.CapacityLimiter(_LIGHT_THREADS)
        _LIGHT_LIMITER.set(limiter)
        return limiter


async def run_core_light[T](fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run ``fn`` on a worker thread without taking the core lock.

    See the module docstring for what qualifies. A cancelled call that already
    started finishes in the background, like ``run_core``.
    """
    return await anyio.to_thread.run_sync(
        partial(fn, *args, **kwargs),
        abandon_on_cancel=True,
        limiter=_light_limiter(),
    )
