from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from hks.core import manifest as manifest_module
from hks.core.manifest import atomic_write


def test_atomic_write_accepts_str_and_bytes(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.json"

    atomic_write(target, "中文\n")
    assert target.read_text(encoding="utf-8") == "中文\n"

    atomic_write(target, b"\x00\x01raw")
    assert target.read_bytes() == b"\x00\x01raw"
    assert sorted(p.name for p in target.parent.iterdir()) == ["file.json"]


def test_atomic_write_uses_unique_temp_in_same_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.json"
    seen: list[str] = []
    real_replace = os.replace

    def spy_replace(src: str, dst: Path) -> None:
        seen.append(src)
        real_replace(src, dst)

    monkeypatch.setattr(manifest_module.os, "replace", spy_replace)
    atomic_write(target, "a")
    atomic_write(target, "b")

    assert len(set(seen)) == 2
    for src in seen:
        assert Path(src).parent == tmp_path
        assert Path(src).name != f"{target.name}.tmp"
    assert target.read_text(encoding="utf-8") == "b"


def test_atomic_write_removes_temp_and_keeps_target_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "page.md"
    target.write_text("original", encoding="utf-8")

    def boom(src: str, dst: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(manifest_module.os, "replace", boom)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write(target, "new")

    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["page.md"]


def test_atomic_write_preserves_existing_mode(tmp_path: Path) -> None:
    target = tmp_path / "mode.txt"
    target.write_text("x", encoding="utf-8")
    target.chmod(0o640)

    atomic_write(target, "y")

    assert target.stat().st_mode & 0o777 == 0o640


def test_atomic_write_concurrent_writers_do_not_collide(tmp_path: Path) -> None:
    target = tmp_path / "shared.json"
    payloads = [f"payload-{index}" * 200 for index in range(16)]
    errors: list[BaseException] = []

    def write(content: str) -> None:
        try:
            for _ in range(20):
                atomic_write(target, content)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(payload,)) for payload in payloads]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert target.read_text(encoding="utf-8") in payloads
    assert [p.name for p in tmp_path.iterdir()] == ["shared.json"]
