from __future__ import annotations

from pathlib import Path

from hks.core.paths import resolve_ks_root, runtime_paths
from hks.core.runtime_context import current_ks_root, scoped_ks_root


def test_scoped_ks_root_overrides_env_and_restores(monkeypatch, tmp_path: Path) -> None:
    env_root = tmp_path / "env-ks"
    scoped_root = tmp_path / "scoped-ks"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    assert resolve_ks_root() == env_root.resolve(strict=False)
    assert current_ks_root() is None

    with scoped_ks_root(scoped_root):
        assert current_ks_root() == scoped_root.resolve(strict=False)
        assert resolve_ks_root() == scoped_root.resolve(strict=False)
        assert runtime_paths().root == scoped_root.resolve(strict=False)

    assert current_ks_root() is None
    assert resolve_ks_root() == env_root.resolve(strict=False)


def test_explicit_root_beats_context_root(tmp_path: Path) -> None:
    scoped_root = tmp_path / "scoped-ks"
    explicit_root = tmp_path / "explicit-ks"

    with scoped_ks_root(scoped_root):
        assert resolve_ks_root(explicit_root) == explicit_root.resolve(strict=False)
        assert runtime_paths(explicit_root).root == explicit_root.resolve(strict=False)


def test_nested_scopes_restore_outer_root(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"

    with scoped_ks_root(outer):
        assert resolve_ks_root() == outer.resolve(strict=False)
        with scoped_ks_root(inner):
            assert resolve_ks_root() == inner.resolve(strict=False)
        assert resolve_ks_root() == outer.resolve(strict=False)
