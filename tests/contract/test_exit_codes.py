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
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted((FIXTURES_ROOT / "valid").iterdir()):
        if child.is_file():
            shutil.copy2(child, target / child.name)
    return target


def _copy_office_docs(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    for name in ("docx", "xlsx", "pptx"):
        shutil.copytree(FIXTURES_ROOT / "valid" / name, target / name)
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
    # Phase 2: pdf sniffing catches missing %PDF- magic before parser runs.
    assert {"path": "broken.pdf", "reason": "corrupt"} in failures


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
def test_ingest_encrypted_office_returns_dataerr_with_valid_json(tmp_path: Path) -> None:
    docs = _copy_office_docs(tmp_path / "docs")
    shutil.copy2(FIXTURES_ROOT / "broken" / "office" / "encrypted.pptx", docs / "encrypted.pptx")

    result = _run_cli("ingest", str(docs), ks_root=tmp_path / "ks")

    assert result.returncode == 65
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    payload = _load_stdout_json(result)
    failures = payload["trace"]["steps"][0]["detail"]["failures"]  # type: ignore[index]
    assert {"path": "encrypted.pptx", "reason": "encrypted"} in failures


@pytest.mark.contract
def test_ingest_corrupt_office_returns_dataerr_with_valid_json(tmp_path: Path) -> None:
    docs = _copy_office_docs(tmp_path / "docs")
    shutil.copy2(FIXTURES_ROOT / "broken" / "office" / "corrupt.xlsx", docs / "corrupt.xlsx")

    result = _run_cli("ingest", str(docs), ks_root=tmp_path / "ks")

    assert result.returncode == 65
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    payload = _load_stdout_json(result)
    failures = payload["trace"]["steps"][0]["detail"]["failures"]  # type: ignore[index]
    assert {"path": "corrupt.xlsx", "reason": "corrupt"} in failures


@pytest.mark.contract
def test_ingest_timeout_office_returns_dataerr_with_valid_json(tmp_path: Path) -> None:
    docs = _copy_office_docs(tmp_path / "docs")
    shutil.copy2(
        FIXTURES_ROOT / "broken" / "office" / "timeout_bomb.docx",
        docs / "timeout_bomb.docx",
    )

    result = _run_cli(
        "ingest",
        str(docs),
        ks_root=tmp_path / "ks",
        extra_env={"HKS_OFFICE_TIMEOUT_SEC": "5"},
    )

    assert result.returncode == 65
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    payload = _load_stdout_json(result)
    failures = payload["trace"]["steps"][0]["detail"]["failures"]  # type: ignore[index]
    assert {"path": "timeout_bomb.docx", "reason": "timeout"} in failures


@pytest.mark.contract
def test_ingest_oversized_office_returns_dataerr_with_valid_json(tmp_path: Path) -> None:
    docs = _copy_office_docs(tmp_path / "docs")
    shutil.copy2(FIXTURES_ROOT / "broken" / "office" / "oversized.xlsx", docs / "oversized.xlsx")

    result = _run_cli(
        "ingest",
        str(docs),
        ks_root=tmp_path / "ks",
        extra_env={"HKS_OFFICE_MAX_FILE_MB": "1"},
    )

    assert result.returncode == 65
    assert result.stderr.splitlines()[0].startswith("[ks:ingest] error:")
    payload = _load_stdout_json(result)
    failures = payload["trace"]["steps"][0]["detail"]["failures"]  # type: ignore[index]
    assert {"path": "oversized.xlsx", "reason": "oversized"} in failures


@pytest.mark.contract
def test_query_hit_returns_zero(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    _seed_runtime(ks_root, tmp_path / "docs")

    result = _run_cli(
        "query",
        "summary Atlas",
        "--writeback=no",
        ks_root=ks_root,
        extra_env={"NO_COLOR": "1"},
    )

    assert result.returncode == 0
    payload = _load_stdout_json(result)
    assert payload["source"] == ["wiki"]


@pytest.mark.contract
def test_query_no_hit_returns_zero(tmp_path: Path) -> None:
    ks_root = tmp_path / "ks"
    _seed_runtime(ks_root, tmp_path / "docs")

    result = _run_cli("query", "明天吃什麼", "--writeback=no", ks_root=ks_root)

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
    rules_path.write_text("version: 1\ndefault_route: matrix\nrules: []\n", encoding="utf-8")

    result = _run_cli(
        "query",
        "summary Atlas",
        "--writeback=no",
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
        "--writeback=no",
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
