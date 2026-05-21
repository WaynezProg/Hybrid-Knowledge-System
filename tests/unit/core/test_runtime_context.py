from __future__ import annotations

from pathlib import Path

import pytest

from hks.core.paths import resolve_ks_root, runtime_paths
from hks.core.runtime_context import (
    current_ks_root,
    reset_current_ks_root,
    scoped_ks_root,
    set_current_ks_root,
)


@pytest.fixture(autouse=True)
def isolated_runtime_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KS_ROOT", raising=False)
    monkeypatch.setenv("HKS_CONFIG_ENV", str(tmp_path / "missing.env"))
    monkeypatch.setenv("HKS_CONFIG_FILE", str(tmp_path / "missing.yaml"))
    monkeypatch.chdir(tmp_path)


def test_set_and_reset_current_ks_root(tmp_path: Path) -> None:
    scoped_root = tmp_path / "scoped-ks"

    token = set_current_ks_root(scoped_root)
    try:
        assert current_ks_root() == scoped_root.resolve(strict=False)
        assert resolve_ks_root() == scoped_root.resolve(strict=False)
    finally:
        reset_current_ks_root(token)

    assert current_ks_root() is None
    assert resolve_ks_root() == (tmp_path / "ks").resolve(strict=False)


def test_set_current_ks_root_none_temporarily_clears_outer_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_root = tmp_path / "env-ks"
    outer = tmp_path / "outer"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    with scoped_ks_root(outer):
        assert resolve_ks_root() == outer.resolve(strict=False)
        token = set_current_ks_root(None)
        try:
            assert current_ks_root() is None
            assert resolve_ks_root() == env_root.resolve(strict=False)
        finally:
            reset_current_ks_root(token)
        assert resolve_ks_root() == outer.resolve(strict=False)


def test_scoped_ks_root_overrides_env_and_restores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_scoped_ks_root_none_temporarily_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_root = tmp_path / "env-ks"
    outer = tmp_path / "outer"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    with scoped_ks_root(outer):
        assert resolve_ks_root() == outer.resolve(strict=False)
        with scoped_ks_root(None):
            assert current_ks_root() is None
            assert resolve_ks_root() == env_root.resolve(strict=False)
        assert resolve_ks_root() == outer.resolve(strict=False)


def test_scoped_ks_root_none_temporarily_falls_back_to_cwd(tmp_path: Path) -> None:
    outer = tmp_path / "outer"

    with scoped_ks_root(outer):
        assert resolve_ks_root() == outer.resolve(strict=False)
        with scoped_ks_root(None):
            assert current_ks_root() is None
            assert resolve_ks_root() == (tmp_path / "ks").resolve(strict=False)
        assert resolve_ks_root() == outer.resolve(strict=False)


def test_explicit_root_beats_context_root(tmp_path: Path) -> None:
    scoped_root = tmp_path / "scoped-ks"
    explicit_root = tmp_path / "explicit-ks"

    with scoped_ks_root(scoped_root):
        assert resolve_ks_root(explicit_root) == explicit_root.resolve(strict=False)
        assert runtime_paths(explicit_root).root == explicit_root.resolve(strict=False)


def test_context_root_beats_env_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_root = tmp_path / "env-ks"
    scoped_root = tmp_path / "scoped-ks"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    with scoped_ks_root(scoped_root):
        assert resolve_ks_root() == scoped_root.resolve(strict=False)
        assert runtime_paths().root == scoped_root.resolve(strict=False)


def test_env_root_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_root = tmp_path / "env-ks"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    assert current_ks_root() is None
    assert resolve_ks_root() == env_root.resolve(strict=False)
    assert runtime_paths().root == env_root.resolve(strict=False)


def test_config_file_root_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_root = tmp_path / "config-ks"
    config_file = tmp_path / "hks.yaml"
    config_file.write_text(f"runtime:\n  ks_root: {config_root}\n", encoding="utf-8")
    monkeypatch.setenv("HKS_CONFIG_FILE", str(config_file))

    assert current_ks_root() is None
    assert resolve_ks_root() == config_root.resolve(strict=False)
    assert runtime_paths().root == config_root.resolve(strict=False)


def test_cwd_root_fallback(tmp_path: Path) -> None:
    assert current_ks_root() is None
    assert resolve_ks_root() == (tmp_path / "ks").resolve(strict=False)
    assert runtime_paths().root == (tmp_path / "ks").resolve(strict=False)


def test_nested_scopes_restore_outer_root(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"

    with scoped_ks_root(outer):
        assert resolve_ks_root() == outer.resolve(strict=False)
        with scoped_ks_root(inner):
            assert resolve_ks_root() == inner.resolve(strict=False)
        assert resolve_ks_root() == outer.resolve(strict=False)
