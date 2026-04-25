from __future__ import annotations

from statistics import quantiles
from time import perf_counter

import pytest

from hks.adapters import core
from hks.core.schema import QueryResponse, Trace, TraceStep


def _response(kind: str = "wiki_lookup") -> QueryResponse:
    return QueryResponse(
        answer="ok",
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind=kind, detail={})]),
    )


@pytest.mark.integration
def test_adapter_wrapper_overhead_p95_under_250ms(monkeypatch) -> None:
    def fake_query(question: str, *, writeback: str) -> QueryResponse:
        return _response()

    def fake_lint(*, strict: bool, severity_threshold: str, fix_mode: str) -> QueryResponse:
        return _response("lint_summary")

    monkeypatch.setattr(core.query_command, "run", fake_query)
    monkeypatch.setattr(core.lint_command, "run", fake_lint)

    durations: list[float] = []
    for _ in range(120):
        start = perf_counter()
        core.hks_query(question="Project Atlas summary")
        core.hks_lint()
        durations.append(perf_counter() - start)

    p95 = quantiles(durations, n=100)[94]
    assert p95 < 0.250
