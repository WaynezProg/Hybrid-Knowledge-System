"""CLI entry for runtime consistency linting."""

from __future__ import annotations

from hks.core.lint_contract import validate_lint_detail
from hks.core.schema import QueryResponse, Trace, TraceStep
from hks.errors import ExitCode, KSError
from hks.lint.models import FixMode, LintResult, SeverityThreshold
from hks.lint.runner import exceeds_threshold, run_lint


def _answer(result: LintResult, *, fix_mode: FixMode) -> str:
    detail = result.to_detail()
    counts = detail["severity_counts"]
    if not result.findings:
        base = "lint 完成：0 issues"
    else:
        base = (
            f"lint 完成：{counts['error']} errors / "
            f"{counts['warning']} warnings / {counts['info']} info"
        )
    if fix_mode == "apply":
        base = f"{base}；applied {len(result.fixes_applied)} / skipped {len(result.fixes_skipped)}"
    return base


def _to_response(result: LintResult, *, fix_mode: FixMode) -> QueryResponse:
    detail = result.to_detail()
    validate_lint_detail(detail)
    return QueryResponse(
        answer=_answer(result, fix_mode=fix_mode),
        source=[],
        confidence=0.0,
        trace=Trace(route="wiki", steps=[TraceStep(kind="lint_summary", detail=detail)]),
    )


def run(
    *,
    strict: bool = False,
    severity_threshold: SeverityThreshold = "error",
    fix_mode: FixMode = "none",
) -> QueryResponse:
    result = run_lint(fix_mode=fix_mode)
    response = _to_response(result, fix_mode=fix_mode)
    if strict and exceeds_threshold(result, severity_threshold):
        raise KSError(
            "lint strict threshold failed",
            exit_code=ExitCode.GENERAL,
            code="LINT_FAILED",
            response=response,
        )
    return response
