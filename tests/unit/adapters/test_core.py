from __future__ import annotations

from hks.adapters import core
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


def test_scoped_ks_root_restores_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KS_ROOT", "/existing/root")

    with core.scoped_ks_root(str(tmp_path / "custom")):
        assert core.os.environ["KS_ROOT"].endswith("/custom")

    assert core.os.environ["KS_ROOT"] == "/existing/root"
