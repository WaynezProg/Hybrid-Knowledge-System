from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMPLE_EMBEDDING_MODEL = "simple"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _cached_model_snapshot(model_name: str) -> Path | None:
    hub_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / f"models--{model_name.replace('/', '--')}"
        / "snapshots"
    )
    if not hub_root.exists():
        return None
    snapshots = sorted(path for path in hub_root.iterdir() if path.is_dir())
    if not snapshots:
        return None
    return snapshots[-1]


@pytest.fixture()
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def tmp_ks_root(tmp_path: Path) -> Path:
    return tmp_path / "ks"


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch, tmp_ks_root: Path) -> None:
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")
    monkeypatch.setenv("KS_ROOT", str(tmp_ks_root))


@pytest.fixture()
def fixtures_root() -> Path:
    return PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture()
def valid_fixtures(fixtures_root: Path) -> Path:
    return fixtures_root / "valid"


@pytest.fixture()
def working_docs(tmp_path: Path, valid_fixtures: Path) -> Path:
    target = tmp_path / "docs"
    shutil.copytree(valid_fixtures, target)
    return target


@pytest.fixture()
def local_embedding_model(monkeypatch: pytest.MonkeyPatch) -> Path | str:
    snapshot = _cached_model_snapshot(DEFAULT_EMBEDDING_MODEL)
    if snapshot is not None:
        monkeypatch.setenv("HKS_EMBEDDING_MODEL", str(snapshot))
        return snapshot
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", SIMPLE_EMBEDDING_MODEL)
    return SIMPLE_EMBEDDING_MODEL
