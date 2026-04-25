"""Shared adapter wrappers around existing command handlers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import validate_tool_input
from hks.adapters.models import (
    FIX_MODES,
    PPTX_NOTES_MODES,
    SEVERITY_THRESHOLDS,
    WRITEBACK_MODES,
    AdapterError,
    AdapterToolError,
    FixMode,
    PptxNotesMode,
    SeverityThreshold,
    WritebackMode,
)
from hks.commands import ingest as ingest_command
from hks.commands import lint as lint_command
from hks.commands import query as query_command
from hks.core.schema import QueryResponse, Route, build_error_response, validate
from hks.errors import ExitCode, KSError


@contextmanager
def scoped_ks_root(ks_root: str | None) -> Iterator[None]:
    if not ks_root:
        yield
        return
    previous = os.environ.get("KS_ROOT")
    os.environ["KS_ROOT"] = str(Path(ks_root).expanduser().resolve(strict=False))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("KS_ROOT", None)
        else:
            os.environ["KS_ROOT"] = previous


def _usage_error(message: str, *, request_id: str | None = None) -> AdapterToolError:
    response = build_error_response(
        message,
        route="wiki",
        code="USAGE",
        exit_code=ExitCode.USAGE,
    )
    return AdapterToolError(
        AdapterError(
            code="USAGE",
            exit_code=ExitCode.USAGE,
            message=message,
            response=response,
            request_id=request_id,
        )
    )


def _route(error: KSError) -> Route:
    if error.route == "vector":
        return "vector"
    if error.route == "graph":
        return "graph"
    return "wiki"


def _to_adapter_error(error: KSError, *, request_id: str | None = None) -> AdapterToolError:
    response = error.response or build_error_response(
        error.message,
        route=_route(error),
        code=error.code,
        exit_code=error.exit_code,
        hint=error.hint,
    )
    return AdapterToolError(
        AdapterError(
            code=error.code,
            exit_code=error.exit_code,
            message=error.message,
            hint=error.hint,
            details=error.details,
            response=response,
            request_id=request_id,
        )
    )


def _run_command(
    handler: Any,
    *args: Any,
    ks_root: str | None = None,
    request_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        with scoped_ks_root(ks_root):
            response = cast(QueryResponse, handler(*args, **kwargs))
    except KSError as error:
        raise _to_adapter_error(error, request_id=request_id) from error
    except Exception as error:
        raise _to_adapter_error(
            KSError(
                str(error),
                exit_code=ExitCode.GENERAL,
                code=type(error).__name__.upper(),
            ),
            request_id=request_id,
        ) from error
    return validate(response.to_dict())


def _require_choice(
    value: str,
    allowed: frozenset[str],
    *,
    field: str,
    request_id: str | None = None,
) -> str:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise _usage_error(
            f"invalid value for {field}: {value}; expected one of {allowed_values}",
            request_id=request_id,
        )
    return value


def hks_query(
    *,
    question: str,
    writeback: str = "no",
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {"question": question, "writeback": writeback, "ks_root": ks_root}
    try:
        validate_tool_input("hks_query", {k: v for k, v in payload.items() if v is not None})
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    mode = cast(WritebackMode, _require_choice(writeback, WRITEBACK_MODES, field="writeback"))
    return _run_command(
        query_command.run,
        question,
        writeback=mode,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_ingest(
    *,
    path: str,
    prune: bool = False,
    pptx_notes: str = "include",
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {"path": path, "prune": prune, "pptx_notes": pptx_notes, "ks_root": ks_root}
    try:
        validate_tool_input("hks_ingest", {k: v for k, v in payload.items() if v is not None})
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    notes = cast(
        PptxNotesMode,
        _require_choice(pptx_notes, PPTX_NOTES_MODES, field="pptx_notes", request_id=request_id),
    )
    return _run_command(
        ingest_command.run,
        Path(path),
        prune=prune,
        pptx_notes=notes == "include",
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_lint(
    *,
    strict: bool = False,
    severity_threshold: str = "error",
    fix: str = "none",
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "strict": strict,
        "severity_threshold": severity_threshold,
        "fix": fix,
        "ks_root": ks_root,
    }
    try:
        validate_tool_input("hks_lint", {k: v for k, v in payload.items() if v is not None})
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    threshold = cast(
        SeverityThreshold,
        _require_choice(
            severity_threshold,
            SEVERITY_THRESHOLDS,
            field="severity_threshold",
            request_id=request_id,
        ),
    )
    fix_mode = cast(FixMode, _require_choice(fix, FIX_MODES, field="fix", request_id=request_id))
    return _run_command(
        lint_command.run,
        strict=strict,
        severity_threshold=threshold,
        fix_mode=fix_mode,
        ks_root=ks_root,
        request_id=request_id,
    )
