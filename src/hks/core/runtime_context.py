"""Request-local runtime context for HKS adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_CURRENT_KS_ROOT: ContextVar[Path | None] = ContextVar("hks_current_ks_root", default=None)


def current_ks_root() -> Path | None:
    """Return the current request-scoped runtime root, if one is active."""

    return _CURRENT_KS_ROOT.get()


@contextmanager
def scoped_ks_root(ks_root: str | Path | None) -> Iterator[None]:
    """Set a request-local KS_ROOT without mutating process environment."""

    if ks_root is None:
        yield
        return

    resolved = Path(ks_root).expanduser().resolve(strict=False)
    token = _CURRENT_KS_ROOT.set(resolved)
    try:
        yield
    finally:
        _CURRENT_KS_ROOT.reset(token)
