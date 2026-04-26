from __future__ import annotations

import shutil
import subprocess
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

_OFFICE_SENTINEL = PROJECT_ROOT / "tests" / "fixtures" / "valid" / "docx" / "plain.docx"
_IMAGE_SENTINEL = (
    PROJECT_ROOT / "tests" / "fixtures" / "valid" / "image" / "atlas-dependency.png"
)


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
    monkeypatch.setenv("HKS_CONFIG_ENV", str(tmp_ks_root / "missing.env"))
    monkeypatch.setenv("HKS_CONFIG_FILE", str(tmp_ks_root / "missing.yaml"))


@pytest.fixture()
def fixtures_root() -> Path:
    return PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture()
def valid_fixtures(fixtures_root: Path) -> Path:
    return fixtures_root / "valid"


def _copy_tree_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir()):
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def _copy_phase1_valid(source: Path, target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir()):
        if child.is_file():
            shutil.copy2(child, target / child.name)
    return target


@pytest.fixture(scope="session", autouse=True)
def ensure_office_fixtures() -> None:
    if _OFFICE_SENTINEL.exists():
        return
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tests" / "fixtures" / "build_office.py")],
        cwd=PROJECT_ROOT,
        check=True,
    )


@pytest.fixture(scope="session", autouse=True)
def ensure_image_fixtures() -> None:
    if _IMAGE_SENTINEL.exists():
        return
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tests" / "fixtures" / "build_images.py")],
        cwd=PROJECT_ROOT,
        check=True,
    )


@pytest.fixture()
def working_docs(tmp_path: Path, valid_fixtures: Path) -> Path:
    target = tmp_path / "docs"
    return _copy_phase1_valid(valid_fixtures, target)


@pytest.fixture()
def working_office_docs(tmp_path: Path, valid_fixtures: Path) -> Path:
    target = tmp_path / "office-docs"
    for name in ("docx", "xlsx", "pptx"):
        _copy_tree_contents(valid_fixtures / name, target / name)
    return target


@pytest.fixture()
def working_all_docs(tmp_path: Path, valid_fixtures: Path) -> Path:
    target = tmp_path / "all-docs"
    _copy_phase1_valid(valid_fixtures, target)
    for name in ("docx", "xlsx", "pptx"):
        _copy_tree_contents(valid_fixtures / name, target / name)
    return target


@pytest.fixture()
def working_image_docs(tmp_path: Path, valid_fixtures: Path) -> Path:
    target = tmp_path / "image-docs"
    _copy_tree_contents(valid_fixtures / "image", target)
    return target


@pytest.fixture()
def working_phase3_docs(tmp_path: Path, valid_fixtures: Path) -> Path:
    target = tmp_path / "phase3-docs"
    _copy_phase1_valid(valid_fixtures, target)
    for name in ("docx", "xlsx", "pptx"):
        _copy_tree_contents(valid_fixtures / name, target / name)
    _copy_tree_contents(valid_fixtures / "image", target / "image")
    return target


@pytest.fixture()
def local_embedding_model(monkeypatch: pytest.MonkeyPatch) -> Path | str:
    snapshot = _cached_model_snapshot(DEFAULT_EMBEDDING_MODEL)
    if snapshot is not None:
        monkeypatch.setenv("HKS_EMBEDDING_MODEL", str(snapshot))
        return snapshot
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", SIMPLE_EMBEDDING_MODEL)
    return SIMPLE_EMBEDDING_MODEL
