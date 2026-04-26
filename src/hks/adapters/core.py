"""Shared adapter wrappers around existing command handlers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from hks.adapters.contracts import (
    validate_coordination_tool_input,
    validate_graphify_tool_input,
    validate_llm_tool_input,
    validate_tool_input,
    validate_watch_tool_input,
    validate_wiki_tool_input,
)
from hks.adapters.models import (
    FIX_MODES,
    GRAPHIFY_MODES,
    LLM_MODES,
    PPTX_NOTES_MODES,
    SEVERITY_THRESHOLDS,
    WATCH_MODES,
    WATCH_PROFILES,
    WIKI_SYNTHESIS_MODES,
    WRITEBACK_MODES,
    AdapterError,
    AdapterToolError,
    FixMode,
    GraphifyMode,
    LlmMode,
    PptxNotesMode,
    SeverityThreshold,
    WatchMode,
    WatchProfile,
    WikiSynthesisMode,
    WritebackMode,
)
from hks.commands import coord as coord_command
from hks.commands import graphify as graphify_command
from hks.commands import ingest as ingest_command
from hks.commands import lint as lint_command
from hks.commands import llm as llm_command
from hks.commands import query as query_command
from hks.commands import watch as watch_command
from hks.commands import wiki as wiki_command
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


def hks_coord_session(
    *,
    action: str,
    agent_id: str,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "action": action,
        "agent_id": agent_id,
        "session_id": session_id,
        "metadata": metadata or {},
        "ks_root": ks_root,
    }
    try:
        validate_coordination_tool_input(
            "hks_coord_session",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    return _run_command(
        coord_command.run_session,
        action=action,
        agent_id=agent_id,
        session_id=session_id,
        metadata=metadata or {},
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_coord_lease(
    *,
    action: str,
    agent_id: str,
    resource_key: str,
    session_id: str | None = None,
    lease_id: str | None = None,
    ttl_seconds: int = 1800,
    reason: str | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "action": action,
        "agent_id": agent_id,
        "resource_key": resource_key,
        "session_id": session_id,
        "lease_id": lease_id,
        "ttl_seconds": ttl_seconds,
        "reason": reason,
        "ks_root": ks_root,
    }
    try:
        validate_coordination_tool_input(
            "hks_coord_lease",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    return _run_command(
        coord_command.run_lease,
        action=action,
        agent_id=agent_id,
        resource_key=resource_key,
        session_id=session_id,
        lease_id=lease_id,
        ttl_seconds=ttl_seconds,
        reason=reason,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_coord_handoff(
    *,
    action: str,
    agent_id: str,
    resource_key: str | None = None,
    summary: str | None = None,
    next_action: str | None = None,
    references: list[dict[str, Any]] | None = None,
    blocked_by: list[str] | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "action": action,
        "agent_id": agent_id,
        "resource_key": resource_key,
        "summary": summary,
        "next_action": next_action,
        "references": references or [],
        "blocked_by": blocked_by or [],
        "ks_root": ks_root,
    }
    try:
        validate_coordination_tool_input(
            "hks_coord_handoff",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    return _run_command(
        coord_command.run_handoff,
        action=action,
        agent_id=agent_id,
        resource_key=resource_key,
        summary=summary,
        next_action=next_action,
        references=references or [],
        blocked_by=blocked_by or [],
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_coord_status(
    *,
    agent_id: str | None = None,
    resource_key: str | None = None,
    include_stale: bool = True,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "agent_id": agent_id,
        "resource_key": resource_key,
        "include_stale": include_stale,
        "ks_root": ks_root,
    }
    try:
        validate_coordination_tool_input(
            "hks_coord_status",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    return _run_command(
        coord_command.run_status,
        agent_id=agent_id,
        resource_key=resource_key,
        include_stale=include_stale,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_llm_classify(
    *,
    source_relpath: str,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    prompt_version: str | None = None,
    force_new_run: bool = False,
    requested_by: str | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source_relpath": source_relpath,
        "mode": mode,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "force_new_run": force_new_run,
        "requested_by": requested_by,
        "ks_root": ks_root,
    }
    try:
        validate_llm_tool_input(
            "hks_llm_classify",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    normalized_mode = cast(
        LlmMode,
        _require_choice(mode, LLM_MODES, field="mode", request_id=request_id),
    )
    return _run_command(
        llm_command.run_classify,
        source_relpath=source_relpath,
        mode=normalized_mode,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        force_new_run=force_new_run,
        requested_by=requested_by,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_wiki_synthesize(
    *,
    mode: str = "preview",
    source_relpath: str | None = None,
    extraction_artifact_id: str | None = None,
    candidate_artifact_id: str | None = None,
    target_slug: str | None = None,
    provider: str = "fake",
    model: str | None = None,
    prompt_version: str | None = None,
    force_new_run: bool = False,
    requested_by: str | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source_relpath": source_relpath,
        "extraction_artifact_id": extraction_artifact_id,
        "candidate_artifact_id": candidate_artifact_id,
        "mode": mode,
        "target_slug": target_slug,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "force_new_run": force_new_run,
        "requested_by": requested_by,
        "ks_root": ks_root,
    }
    try:
        validate_wiki_tool_input(
            "hks_wiki_synthesize",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    normalized_mode = cast(
        WikiSynthesisMode,
        _require_choice(mode, WIKI_SYNTHESIS_MODES, field="mode", request_id=request_id),
    )
    return _run_command(
        wiki_command.run_synthesize,
        mode=normalized_mode,
        source_relpath=source_relpath,
        extraction_artifact_id=extraction_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
        target_slug=target_slug,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        force_new_run=force_new_run,
        requested_by=requested_by,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_graphify_build(
    *,
    mode: str = "preview",
    provider: str = "fake",
    model: str | None = None,
    algorithm_version: str | None = None,
    include_html: bool = True,
    include_report: bool = True,
    force_new_run: bool = False,
    requested_by: str | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "mode": mode,
        "provider": provider,
        "model": model,
        "algorithm_version": algorithm_version,
        "include_html": include_html,
        "include_report": include_report,
        "force_new_run": force_new_run,
        "requested_by": requested_by,
        "ks_root": ks_root,
    }
    try:
        validate_graphify_tool_input(
            "hks_graphify_build",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    normalized_mode = cast(
        GraphifyMode,
        _require_choice(mode, GRAPHIFY_MODES, field="mode", request_id=request_id),
    )
    return _run_command(
        graphify_command.run_build,
        mode=normalized_mode,
        provider=provider,
        model=model,
        algorithm_version=algorithm_version,
        include_html=include_html,
        include_report=include_report,
        force_new_run=force_new_run,
        requested_by=requested_by,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_watch_scan(
    *,
    source_roots: list[str] | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ks_root": ks_root, "request_id": request_id}
    if source_roots:
        payload["source_roots"] = source_roots
    try:
        validate_watch_tool_input(
            "hks_watch_scan",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    return _run_command(
        watch_command.run_scan,
        source_roots=[Path(root) for root in source_roots or []],
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_watch_run(
    *,
    mode: str = "dry-run",
    profile: str = "scan-only",
    source_roots: list[str] | None = None,
    prune: bool = False,
    include_llm: bool = False,
    include_wiki_apply: bool = False,
    include_graphify: bool = False,
    force: bool = False,
    requested_by: str | None = None,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {
        "mode": mode,
        "profile": profile,
        "prune": prune,
        "include_llm": include_llm,
        "include_wiki_apply": include_wiki_apply,
        "include_graphify": include_graphify,
        "force": force,
        "requested_by": requested_by,
        "ks_root": ks_root,
        "request_id": request_id,
    }
    if source_roots:
        payload["source_roots"] = source_roots
    try:
        validate_watch_tool_input(
            "hks_watch_run",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    normalized_mode = cast(
        WatchMode,
        _require_choice(mode, WATCH_MODES, field="mode", request_id=request_id),
    )
    normalized_profile = cast(
        WatchProfile,
        _require_choice(profile, WATCH_PROFILES, field="profile", request_id=request_id),
    )
    return _run_command(
        watch_command.run_watch,
        source_roots=[Path(root) for root in source_roots or []],
        mode=normalized_mode,
        profile=normalized_profile,
        prune=prune,
        include_llm=include_llm,
        include_wiki_apply=include_wiki_apply,
        include_graphify=include_graphify,
        force=force,
        requested_by=requested_by,
        ks_root=ks_root,
        request_id=request_id,
    )


def hks_watch_status(
    *,
    ks_root: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload = {"ks_root": ks_root, "request_id": request_id}
    try:
        validate_watch_tool_input(
            "hks_watch_status",
            {key: value for key, value in payload.items() if value is not None},
        )
    except Exception as error:
        raise _usage_error(str(error), request_id=request_id) from error
    return _run_command(
        watch_command.run_status,
        ks_root=ks_root,
        request_id=request_id,
    )
