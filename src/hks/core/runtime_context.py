"""Request-local runtime context for HKS adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

_CURRENT_KS_ROOT: ContextVar[Path | None] = ContextVar("hks_current_ks_root", default=None)


def current_ks_root() -> Path | None:
    """Return the current request-scoped runtime root, if one is active."""

    return _CURRENT_KS_ROOT.get()


def set_current_ks_root(root: str | Path | None) -> Token[Path | None]:
    """Set the current request-scoped runtime root and return a reset token."""

    if root is None:
        return _CURRENT_KS_ROOT.set(None)

    resolved = Path(root).expanduser().resolve(strict=False)
    return _CURRENT_KS_ROOT.set(resolved)


def reset_current_ks_root(token: Token[Path | None]) -> None:
    """Restore the request-scoped runtime root from a token."""

    _CURRENT_KS_ROOT.reset(token)


@contextmanager
def scoped_ks_root(ks_root: str | Path | None) -> Iterator[None]:
    """Set a request-local KS_ROOT without mutating process environment."""

    token = set_current_ks_root(ks_root)
    try:
        yield
    finally:
        reset_current_ks_root(token)
