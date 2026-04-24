from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from hks.core.lock import file_lock
from hks.core.paths import runtime_paths
from hks.core.schema import validate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = PROJECT_ROOT / "tests" / "fixtures"


def _run_cli(
    *args: str,
    ks_root: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["KS_ROOT"] = str(ks_root)
    env.setdefault("HKS_EMBEDDING_MODEL", "simple")
    existing_pythonpath = env.get("PYTHONPATH")
    src_path = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not existing_pythonpath else os.pathsep.join([src_path, existing_pythonpath])
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "hks.cli", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _copy_valid_docs(target: Path) -> Path:
    shutil.copytree(FIXTURES_ROOT / "valid", target)
    return target


def _seed_runtime(ks_root: Path, docs_dir: Path) -> None:
    result = _run_cli("ingest", str(_copy_valid_docs(docs_dir)), ks_root=ks_root)
    assert result.returncode == 0, result.stderr


def _load_stdout_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    payload = cast(dict[str, Any], json.loads(result.stdout))
    validate(payload)
    return payload


@pytest.mark.contract
def test_ingest_success_exit_zero(tmp_path: Path) -> None:
    result = _run_cli(
        "ingest",
        str(_copy_valid_docs(tmp_path / "docs")),
        ks_root=tmp_path / "ks",
    )

    assert result.returncode == 0
    payload = _load_stdout_json(result)
    detail = payload["trace"]["steps"][0]["detail"]  # type: ignore[index]
    assert len(detail["created"]) == 10  # type: ignore[index]


@pytest.mark.contract
def test_ingest_partial_failure_returns_dataerr(tmp_path: Path) -> None:
    docs = _copy_valid_docs(tmp_path / "docs")
    shutil.copy2(FIXTURES_ROOT / "broken" / "broken.pdf", docs / "broken.pdf")

    result = _run_cli("ingest", str(docs), ks_root=tmp_path / "ks")

    assert result.returncode == 65
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    payload = _load_stdout_json(result)
    failures = payload["trace"]["steps"][0]["detail"]["failures"]  # type: ignore[index]
    assert {"path": "broken.pdf", "reason": "pdf_read_error"} in failures


@pytest.mark.contract
def test_ingest_missing_path_returns_noinput(tmp_path: Path) -> None:
    result = _run_cli("ingest", str(tmp_path / "missing"), ks_root=tmp_path / "ks")

    assert result.returncode == 66
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    _load_stdout_json(result)


@pytest.mark.contract
def test_ingest_usage_error_returns_two(tmp_path: Path) -> None:
    result = _run_cli("ingest", "--unknown-option", ks_root=tmp_path / "ks")

    assert result.returncode == 2
    assert "No such option" in result.stderr
    assert result.stdout == ""


@pytest.mark.contract
def test_ingest_locked_runtime_returns_general(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    lock_path = runtime_paths(ks_root).lock
    docs = _copy_valid_docs(tmp_path / "docs")

    with file_lock(lock_path):
        result = _run_cli("ingest", str(docs), ks_root=ks_root)

    assert result.returncode == 1
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    _load_stdout_json(result)


@pytest.mark.contract
def test_ingest_manifest_write_failure_returns_general(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    manifest_dir = ks_root / "manifest.json"
    manifest_dir.mkdir(parents=True)

    result = _run_cli(
        "ingest",
        str(_copy_valid_docs(tmp_path / "docs")),
        ks_root=ks_root,
    )

    assert result.returncode == 1
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    _load_stdout_json(result)


@pytest.mark.contract
def test_query_hit_returns_zero(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    _seed_runtime(ks_root, tmp_path / "docs")

    result = _run_cli("query", "summary Atlas", ks_root=ks_root, extra_env={"NO_COLOR": "1"})

    assert result.returncode == 0
    payload = _load_stdout_json(result)
    assert payload["source"] == ["wiki"]


@pytest.mark.contract
def test_query_no_hit_returns_zero(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    _seed_runtime(ks_root, tmp_path / "docs")

    result = _run_cli("query", "明天吃什麼", ks_root=ks_root)

    assert result.returncode == 0
    payload = _load_stdout_json(result)
    assert payload["answer"] == "未能於現有知識中找到答案"
    assert payload["source"] == []


@pytest.mark.contract
def test_query_uninitialized_returns_noinput(tmp_path: Path) -> None:
    result = _run_cli("query", "atlas summary", ks_root=tmp_path / "ks")

    assert result.returncode == 66
    assert result.stderr.splitlines()[0].startswith("[ks:query] error:")
    _load_stdout_json(result)


@pytest.mark.contract
def test_query_invalid_rules_returns_general(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    _seed_runtime(ks_root, tmp_path / "docs")
    rules_path = tmp_path / "bad-routing.yaml"
    rules_path.write_text("version: 1\ndefault_route: graph\nrules: []\n", encoding="utf-8")

    result = _run_cli(
        "query",
        "summary Atlas",
        ks_root=ks_root,
        extra_env={"HKS_ROUTING_RULES": str(rules_path)},
    )

    assert result.returncode == 1
    assert result.stderr.splitlines()[0].startswith("[ks:query] error:")
    _load_stdout_json(result)


@pytest.mark.contract
def test_query_usage_error_returns_two(tmp_path: Path) -> None:
    result = _run_cli("query", "atlas", "--unknown-option", ks_root=tmp_path / "ks")

    assert result.returncode == 2
    assert "No such option" in result.stderr
    assert result.stdout == ""


@pytest.mark.contract
def test_query_embedding_load_failure_returns_general(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    _seed_runtime(ks_root, tmp_path / "docs")

    result = _run_cli(
        "query",
        "clause 3.2 text",
        ks_root=ks_root,
        extra_env={
            "HKS_EMBEDDING_MODEL": "missing-local-model",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
    )

    assert result.returncode == 1
    assert result.stderr.splitlines()[0].startswith("[ks:query] error:")
    _load_stdout_json(result)


@pytest.mark.contract
def test_lint_exit_code_is_zero(tmp_path: Path) -> None:
    result = _run_cli("lint", ks_root=tmp_path / "ks")

    assert result.returncode == 0
    payload = _load_stdout_json(result)
    assert payload["answer"] == "lint 尚未實作，預計於 Phase 3 提供"


@pytest.mark.contract
def test_lint_usage_error_returns_two(tmp_path: Path) -> None:
    result = _run_cli("lint", "--unknown-option", ks_root=tmp_path / "ks")

    assert result.returncode == 2
    assert "No such option" in result.stderr
    assert result.stdout == ""
