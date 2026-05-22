from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hks.core.hashing import stable_content_hash, stable_json_hash
from hks.core.lock import blocking_file_lock


@pytest.mark.unit
def test_stable_json_hash_is_order_stable_and_can_truncate() -> None:
    payload = {"b": [2, {"d": 4, "c": 3}], "a": "Atlas"}
    reordered = {"a": "Atlas", "b": [2, {"c": 3, "d": 4}]}

    assert stable_json_hash(payload) == stable_json_hash(reordered)
    assert stable_json_hash(payload, length=12) == stable_json_hash(reordered)[:12]


@pytest.mark.unit
def test_stable_content_hash_accepts_text_and_bytes() -> None:
    assert stable_content_hash("Atlas") == stable_content_hash(b"Atlas")
    assert len(stable_content_hash("Atlas")) == 64


@pytest.mark.unit
def test_blocking_file_lock_waits_until_holder_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "artifact.lock"
    marker_path = tmp_path / "acquired.txt"
    project_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{project_root / 'src'}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(project_root / "src")
    )
    code = """
from pathlib import Path
import sys
from hks.core.lock import blocking_file_lock

with blocking_file_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text("acquired", encoding="utf-8")
"""

    with blocking_file_lock(lock_path):
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(lock_path), str(marker_path)],
            cwd=project_root,
            env=env,
        )
        time.sleep(0.2)
        assert not marker_path.exists()

    process.wait(timeout=5)
    assert process.returncode == 0
    assert marker_path.read_text(encoding="utf-8") == "acquired"
