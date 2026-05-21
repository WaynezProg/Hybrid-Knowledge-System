from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from hks.adapters import core
from hks.commands import query as query_command
from hks.core.manifest import Manifest, save_manifest
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace
from hks.workspace import service as workspace_service


def _response(answer: str) -> QueryResponse:
    return QueryResponse(
        answer=answer,
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki"),
    )


def _make_ready_root(ks_root: Path) -> None:
    paths = runtime_paths(ks_root)
    paths.root.mkdir(parents=True, exist_ok=True)
    save_manifest(Manifest(), paths.manifest)


@pytest.mark.integration
def test_workspace_query_uses_context_without_env_mutation(monkeypatch, tmp_path) -> None:
    env_root = tmp_path / "env-ks"
    ks_root = tmp_path / "workspace-ks"
    registry = tmp_path / "workspaces.json"
    _make_ready_root(ks_root)
    monkeypatch.setenv("KS_ROOT", str(env_root))
    workspace_service.register_workspace(
        "proj-a",
        ks_root=ks_root,
        registry_path_value=registry,
    )

    def fake_run(question: str, *, writeback: str) -> QueryResponse:
        assert runtime_paths().root == ks_root.resolve(strict=False)
        assert question == "What changed?"
        assert writeback == "no"
        assert os.environ["KS_ROOT"] == str(env_root)
        return _response("workspace answer")

    monkeypatch.setattr(query_command, "run", fake_run)

    response = workspace_service.query_workspace(
        "proj-a",
        "What changed?",
        writeback="no",
        registry_path_value=registry,
    )

    assert response.answer == "workspace answer"
    assert os.environ["KS_ROOT"] == str(env_root)


@pytest.mark.integration
def test_parallel_adapter_queries_keep_distinct_roots(monkeypatch, tmp_path) -> None:
    root_a = tmp_path / "ks-a"
    root_b = tmp_path / "ks-b"
    env_root = tmp_path / "env-ks"
    monkeypatch.setenv("KS_ROOT", str(env_root))
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    seen: dict[str, Path] = {}

    def fake_run(question: str, *, writeback: str) -> QueryResponse:
        root = runtime_paths().root
        barrier.wait(timeout=5)
        with lock:
            seen[question] = root
        return _response(f"{question}:{root.name}:{writeback}")

    monkeypatch.setattr(query_command, "run", fake_run)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(
            core.hks_query,
            question="qa",
            writeback="no",
            ks_root=str(root_a),
        )
        future_b = executor.submit(
            core.hks_query,
            question="qb",
            writeback="auto",
            ks_root=str(root_b),
        )
        result_a = future_a.result(timeout=10)
        result_b = future_b.result(timeout=10)

    assert result_a["answer"] == "qa:ks-a:no"
    assert result_b["answer"] == "qb:ks-b:auto"
    assert seen == {
        "qa": root_a.resolve(strict=False),
        "qb": root_b.resolve(strict=False),
    }
    assert os.environ["KS_ROOT"] == str(env_root)
