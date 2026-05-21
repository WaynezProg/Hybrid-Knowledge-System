from __future__ import annotations

import os

from hks.adapters import core
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace, TraceStep


def _response() -> QueryResponse:
    return QueryResponse(
        answer="Atlas summary",
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="wiki_lookup", detail={"hit": True})]),
    )


def test_successful_query_wrapper_returns_direct_query_response(monkeypatch) -> None:
    def fake_run(question: str, *, writeback: str) -> QueryResponse:
        assert question == "Project Atlas"
        assert writeback == "no"
        return _response()

    monkeypatch.setattr(core.query_command, "run", fake_run)

    payload = core.hks_query(question="Project Atlas")

    assert payload["answer"] == "Atlas summary"
    assert payload["source"] == ["wiki"]
    assert "ok" not in payload
    assert "payload" not in payload


def test_hks_query_uses_scoped_ks_root_without_mutating_environment(monkeypatch, tmp_path) -> None:
    env_root = tmp_path / "existing-root"
    scoped_root = tmp_path / "scoped-root"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    def fake_run(question: str, *, writeback: str) -> QueryResponse:
        assert question == "Project Atlas"
        assert writeback == "no"
        assert runtime_paths().root == scoped_root.resolve(strict=False)
        assert os.environ["KS_ROOT"] == str(env_root)
        assert os.environ["KS_ROOT"] != str(scoped_root.resolve(strict=False))
        return _response()

    monkeypatch.setattr(core.query_command, "run", fake_run)

    payload = core.hks_query(question="Project Atlas", ks_root=str(scoped_root))

    assert payload["answer"] == "Atlas summary"
    assert os.environ["KS_ROOT"] == str(env_root)
    assert os.environ["KS_ROOT"] != str(scoped_root.resolve(strict=False))
