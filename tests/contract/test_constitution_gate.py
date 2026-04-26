from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "hks"
FORBIDDEN_HOSTED_VENDOR_IMPORTS = (
    "from openai",
    "import openai",
    "from anthropic",
    "import anthropic",
)


@pytest.mark.contract
def test_src_has_no_hosted_vendor_sdk_dependencies() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lowered = line.lower()
            if any(token in lowered for token in FORBIDDEN_HOSTED_VENDOR_IMPORTS):
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}: {line.strip()}")
    assert violations == []


@pytest.mark.contract
def test_smoke_runtime_graph_directory_is_json_backed() -> None:
    graph_dirs = sorted(
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in PROJECT_ROOT.glob(".ks-smoke/**/graph")
        if path.is_dir()
    )
    for graph_dir in graph_dirs:
        assert (PROJECT_ROOT / graph_dir / "graph.json").exists()
