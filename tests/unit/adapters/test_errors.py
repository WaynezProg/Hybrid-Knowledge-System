from __future__ import annotations

import pytest

from hks.adapters import core
from hks.adapters.contracts import validate_adapter_error
from hks.adapters.models import AdapterToolError
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError


def test_kserror_maps_to_adapter_error_envelope(monkeypatch) -> None:
    response = QueryResponse(
        answer="bad data",
        source=[],
        confidence=0.0,
        trace=Trace(
            route="wiki",
            steps=[TraceStep(kind="error", detail={"code": "DATAERR", "exit_code": 65})],
        ),
    )

    def fake_run(*, strict: bool, severity_threshold: str, fix_mode: str) -> QueryResponse:
        raise KSError(
            "lint failed",
            exit_code=ExitCode.DATAERR,
            code="DATAERR",
            details=["bad.json"],
            response=response,
        )

    monkeypatch.setattr(core.lint_command, "run", fake_run)

    with pytest.raises(AdapterToolError) as exc_info:
        core.hks_lint(request_id="req-42")

    envelope = exc_info.value.to_dict()
    validate_adapter_error(envelope)
    assert envelope["request_id"] == "req-42"
    assert envelope["error"]["code"] == "DATAERR"
    assert envelope["error"]["exit_code"] == 65
    assert envelope["error"]["details"] == ["bad.json"]
    assert envelope["response"]["answer"] == "bad data"


def test_unexpected_exception_maps_to_general_error(monkeypatch) -> None:
    def fake_run(question: str, *, writeback: str) -> QueryResponse:
        raise RuntimeError("boom")

    monkeypatch.setattr(core.query_command, "run", fake_run)

    with pytest.raises(AdapterToolError) as exc_info:
        core.hks_query(question="Project Atlas")

    envelope = exc_info.value.to_dict()
    validate_adapter_error(envelope)
    assert envelope["error"]["code"] == "RUNTIMEERROR"
    assert envelope["error"]["exit_code"] == 1
