"""Top-level Typer app for the HKS CLI."""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn, cast

import typer

from hks import __version__
from hks.commands import coord as coord_command
from hks.commands import ingest as ingest_command
from hks.commands import lint as lint_command
from hks.commands import llm as llm_command
from hks.commands import query as query_command
from hks.commands import wiki as wiki_command
from hks.core.schema import QueryResponse, Route, build_error_response
from hks.errors import ExitCode, KSError
from hks.lint.models import FixMode, SeverityThreshold

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
coord_app = typer.Typer(add_completion=False, no_args_is_help=True)
llm_app = typer.Typer(add_completion=False, no_args_is_help=True)
wiki_app = typer.Typer(add_completion=False, no_args_is_help=True)
coord_session_app = typer.Typer(add_completion=False, no_args_is_help=True)
coord_lease_app = typer.Typer(add_completion=False, no_args_is_help=True)
coord_handoff_app = typer.Typer(add_completion=False, no_args_is_help=True)
coord_app.add_typer(coord_session_app, name="session")
coord_app.add_typer(coord_lease_app, name="lease")
coord_app.add_typer(coord_handoff_app, name="handoff")
app.add_typer(coord_app, name="coord")
app.add_typer(llm_app, name="llm")
app.add_typer(wiki_app, name="wiki")


class WritebackMode(StrEnum):
    auto = "auto"
    yes = "yes"
    no = "no"
    ask = "ask"


class PptxNotesMode(StrEnum):
    include = "include"
    exclude = "exclude"


class LlmMode(StrEnum):
    preview = "preview"
    store = "store"


class WikiSynthesisMode(StrEnum):
    preview = "preview"
    store = "store"
    apply = "apply"


def version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(code=int(ExitCode.OK))


@app.callback()
def callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    _ = version


def emit_response(response: QueryResponse) -> None:
    typer.echo(response.to_json())


def emit_error(command: str, error: KSError) -> NoReturn:
    route: Route = "wiki"
    if error.route == "vector":
        route = "vector"
    typer.echo(error.stderr_message(command), err=True)
    if error.response is not None:
        emit_response(error.response)
    else:
        emit_response(
            build_error_response(
                error.message,
                route=route,
                code=error.code,
                exit_code=error.exit_code,
                hint=error.hint,
            )
        )
    raise typer.Exit(code=int(error.exit_code))


def run_command[T: QueryResponse](
    command: str,
    handler: Callable[..., T],
    *args: object,
    **kwargs: object,
) -> None:
    try:
        response = handler(*args, **kwargs)
    except KSError as error:
        emit_error(command, error)
    except Exception as error:  # pragma: no cover - defensive fallback
        emit_error(
            command,
            KSError(
                str(error),
                exit_code=ExitCode.GENERAL,
                code=type(error).__name__.upper(),
            ),
        )

    emit_response(response)


@app.command("ingest")
def ingest(
    path: Annotated[Path, typer.Argument(help="File or directory to ingest.")],
    prune: Annotated[
        bool,
        typer.Option(
            "--prune",
            help="Delete artifacts for files missing from the source directory.",
        ),
    ] = False,
    pptx_notes: Annotated[
        PptxNotesMode,
        typer.Option(
            "--pptx-notes",
            case_sensitive=False,
            help="Include or exclude pptx speaker notes (default: include).",
        ),
    ] = PptxNotesMode.include,
) -> None:
    from hks.ingest.guards import load_image_limits, load_office_limits

    try:
        load_office_limits()
        load_image_limits()
    except ValueError as error:
        raise typer.Exit(code=_emit_usage_error("ingest", str(error))) from error
    run_command(
        "ingest",
        ingest_command.run,
        path,
        prune=prune,
        pptx_notes=pptx_notes == PptxNotesMode.include,
    )


def _emit_usage_error(command: str, message: str) -> int:
    typer.echo(f"[ks:{command}] usage: {message}", err=True)
    emit_response(
        build_error_response(
            message,
            route="wiki",
            code="USAGE",
            exit_code=ExitCode.USAGE,
            hint=None,
        )
    )
    return int(ExitCode.USAGE)


@app.command("query")
def query(
    question: Annotated[str, typer.Argument(help="Question to ask the knowledge base.")],
    writeback: Annotated[
        WritebackMode,
        typer.Option(
            "--writeback",
            case_sensitive=False,
            help="Override write-back behavior.",
        ),
    ] = WritebackMode.auto,
) -> None:
    run_command("query", query_command.run, question, writeback=writeback.value)


@llm_app.command("classify")
def llm_classify(
    source_relpath: Annotated[str, typer.Argument(help="Ingested source relpath.")],
    mode: Annotated[
        LlmMode,
        typer.Option("--mode", case_sensitive=False, help="Extraction mode."),
    ] = LlmMode.preview,
    provider: Annotated[str, typer.Option("--provider", help="LLM provider id.")] = "fake",
    model: Annotated[str | None, typer.Option("--model", help="Provider model id.")] = None,
    prompt_version: Annotated[
        str | None,
        typer.Option("--prompt-version", help="Prompt contract version."),
    ] = None,
    force_new_run: Annotated[
        bool,
        typer.Option("--force-new-run", help="Do not reuse an existing stored artifact."),
    ] = False,
    requested_by: Annotated[
        str | None,
        typer.Option("--requested-by", help="Agent or user label for audit."),
    ] = None,
) -> None:
    run_command(
        "llm classify",
        llm_command.run_classify,
        source_relpath=source_relpath,
        mode=mode.value,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        force_new_run=force_new_run,
        requested_by=requested_by,
    )


@wiki_app.command("synthesize")
def wiki_synthesize(
    source_relpath: Annotated[
        str | None,
        typer.Option("--source-relpath", help="Ingested source relpath."),
    ] = None,
    extraction_artifact_id: Annotated[
        str | None,
        typer.Option("--extraction-artifact-id", help="Stored 008 extraction artifact id."),
    ] = None,
    candidate_artifact_id: Annotated[
        str | None,
        typer.Option("--candidate-artifact-id", help="Stored 009 candidate artifact id."),
    ] = None,
    mode: Annotated[
        WikiSynthesisMode,
        typer.Option("--mode", case_sensitive=False, help="Wiki synthesis mode."),
    ] = WikiSynthesisMode.preview,
    target_slug: Annotated[
        str | None,
        typer.Option("--target-slug", help="Requested wiki page slug."),
    ] = None,
    provider: Annotated[str, typer.Option("--provider", help="LLM provider id.")] = "fake",
    model: Annotated[str | None, typer.Option("--model", help="Provider model id.")] = None,
    prompt_version: Annotated[
        str | None,
        typer.Option("--prompt-version", help="Prompt contract version."),
    ] = None,
    force_new_run: Annotated[
        bool,
        typer.Option("--force-new-run", help="Do not reuse an existing stored candidate."),
    ] = False,
    requested_by: Annotated[
        str | None,
        typer.Option("--requested-by", help="Agent or user label for audit."),
    ] = None,
) -> None:
    run_command(
        "wiki synthesize",
        wiki_command.run_synthesize,
        source_relpath=source_relpath,
        extraction_artifact_id=extraction_artifact_id,
        candidate_artifact_id=candidate_artifact_id,
        mode=mode.value,
        target_slug=target_slug,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        force_new_run=force_new_run,
        requested_by=requested_by,
    )


@app.command(
    "lint",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def lint(ctx: typer.Context) -> None:
    try:
        strict, severity_threshold, fix_mode = _parse_lint_args(list(ctx.args))
    except ValueError as error:
        raise typer.Exit(code=_emit_usage_error("lint", str(error))) from error
    run_command(
        "lint",
        lint_command.run,
        strict=strict,
        severity_threshold=severity_threshold,
        fix_mode=fix_mode,
    )


def _parse_lint_args(args: list[str]) -> tuple[bool, SeverityThreshold, FixMode]:
    strict = False
    severity_threshold: SeverityThreshold = "error"
    fix_mode: FixMode = "none"
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--strict":
            strict = True
            index += 1
            continue
        if arg == "--severity-threshold":
            if index + 1 >= len(args):
                raise ValueError("missing value for --severity-threshold")
            severity_threshold = _parse_severity_threshold(args[index + 1])
            index += 2
            continue
        if arg.startswith("--severity-threshold="):
            severity_threshold = _parse_severity_threshold(arg.split("=", 1)[1])
            index += 1
            continue
        if arg == "--fix":
            if index + 1 < len(args) and not args[index + 1].startswith("--"):
                fix_mode = _parse_fix_mode(args[index + 1])
                index += 2
            else:
                fix_mode = "plan"
                index += 1
            continue
        if arg.startswith("--fix="):
            fix_mode = _parse_fix_mode(arg.split("=", 1)[1])
            index += 1
            continue
        raise ValueError(f"unknown option for lint: {arg}")
    return strict, severity_threshold, fix_mode


def _parse_severity_threshold(value: str) -> SeverityThreshold:
    if value not in {"error", "warning", "info"}:
        raise ValueError(f"invalid value for --severity-threshold: {value}")
    return cast(SeverityThreshold, value)


def _parse_fix_mode(value: str) -> FixMode:
    if value == "":
        return "plan"
    if value not in {"plan", "apply"}:
        raise ValueError(f"invalid value for --fix: {value}")
    return cast(FixMode, value)


def _parse_json_object(value: str | None, *, field: str) -> dict[str, object]:
    if not value:
        return {}
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be a JSON object")
    return cast(dict[str, object], payload)


def _parse_json_array(value: str | None, *, field: str) -> list[dict[str, object]]:
    if not value:
        return []
    payload = json.loads(value)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ValueError(f"{field} must be a JSON array of objects")
    return cast(list[dict[str, object]], payload)


@coord_session_app.command("start")
def coord_session_start(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    metadata: Annotated[
        str | None,
        typer.Option("--metadata", help="Session metadata JSON object."),
    ] = None,
) -> None:
    try:
        parsed_metadata = _parse_json_object(metadata, field="metadata")
    except (json.JSONDecodeError, ValueError) as error:
        raise typer.Exit(code=_emit_usage_error("coord", str(error))) from error
    run_command(
        "coord",
        coord_command.run_session,
        action="start",
        agent_id=agent_id,
        metadata=parsed_metadata,
    )


@coord_session_app.command("heartbeat")
def coord_session_heartbeat(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Session id to heartbeat."),
    ] = None,
) -> None:
    run_command(
        "coord",
        coord_command.run_session,
        action="heartbeat",
        agent_id=agent_id,
        session_id=session_id,
    )


@coord_session_app.command("close")
def coord_session_close(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Session id to close."),
    ] = None,
) -> None:
    run_command(
        "coord",
        coord_command.run_session,
        action="close",
        agent_id=agent_id,
        session_id=session_id,
    )


@coord_lease_app.command("claim")
def coord_lease_claim(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    resource_key: Annotated[str, typer.Argument(help="Logical resource key.")],
    session_id: Annotated[
        str | None,
        typer.Option("--session-id", help="Owner session id."),
    ] = None,
    ttl_seconds: Annotated[
        int,
        typer.Option("--ttl-seconds", help="Lease ttl in seconds."),
    ] = 1800,
    reason: Annotated[str | None, typer.Option("--reason", help="Lease reason.")] = None,
) -> None:
    run_command(
        "coord",
        coord_command.run_lease,
        action="claim",
        agent_id=agent_id,
        resource_key=resource_key,
        session_id=session_id,
        ttl_seconds=ttl_seconds,
        reason=reason,
    )


@coord_lease_app.command("renew")
def coord_lease_renew(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    resource_key: Annotated[str, typer.Argument(help="Logical resource key.")],
    lease_id: Annotated[str | None, typer.Option("--lease-id", help="Lease id.")] = None,
    ttl_seconds: Annotated[
        int,
        typer.Option("--ttl-seconds", help="Lease ttl in seconds."),
    ] = 1800,
    reason: Annotated[str | None, typer.Option("--reason", help="Lease reason.")] = None,
) -> None:
    run_command(
        "coord",
        coord_command.run_lease,
        action="renew",
        agent_id=agent_id,
        resource_key=resource_key,
        lease_id=lease_id,
        ttl_seconds=ttl_seconds,
        reason=reason,
    )


@coord_lease_app.command("release")
def coord_lease_release(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    resource_key: Annotated[str, typer.Argument(help="Logical resource key.")],
    lease_id: Annotated[str | None, typer.Option("--lease-id", help="Lease id.")] = None,
) -> None:
    run_command(
        "coord",
        coord_command.run_lease,
        action="release",
        agent_id=agent_id,
        resource_key=resource_key,
        lease_id=lease_id,
    )


@coord_handoff_app.command("add")
def coord_handoff_add(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    summary: Annotated[str, typer.Option("--summary", help="Handoff summary.")],
    next_action: Annotated[str, typer.Option("--next-action", help="Next action.")],
    resource_key: Annotated[
        str | None,
        typer.Option("--resource-key", help="Logical resource key."),
    ] = None,
    references: Annotated[
        str | None,
        typer.Option("--references", help="Resource references JSON array."),
    ] = None,
    blocked_by: Annotated[
        list[str] | None,
        typer.Option("--blocked-by", help="Blocking item."),
    ] = None,
) -> None:
    try:
        parsed_references = _parse_json_array(references, field="references")
    except (json.JSONDecodeError, ValueError) as error:
        raise typer.Exit(code=_emit_usage_error("coord", str(error))) from error
    run_command(
        "coord",
        coord_command.run_handoff,
        action="add",
        agent_id=agent_id,
        resource_key=resource_key,
        summary=summary,
        next_action=next_action,
        references=parsed_references,
        blocked_by=blocked_by or [],
    )


@coord_handoff_app.command("list")
def coord_handoff_list(
    agent_id: Annotated[str, typer.Argument(help="Agent identifier.")],
    resource_key: Annotated[
        str | None,
        typer.Option("--resource-key", help="Logical resource key."),
    ] = None,
) -> None:
    run_command(
        "coord",
        coord_command.run_handoff,
        action="list",
        agent_id=agent_id,
        resource_key=resource_key,
    )


@coord_app.command("status")
def coord_status(
    agent_id: Annotated[
        str | None,
        typer.Option("--agent-id", help="Filter by agent id."),
    ] = None,
    resource_key: Annotated[
        str | None,
        typer.Option("--resource-key", help="Filter by resource key."),
    ] = None,
    include_stale: Annotated[
        bool,
        typer.Option("--include-stale/--hide-stale", help="Include stale sessions."),
    ] = True,
) -> None:
    run_command(
        "coord",
        coord_command.run_status,
        agent_id=agent_id,
        resource_key=resource_key,
        include_stale=include_stale,
    )


@coord_app.command("lint")
def coord_lint() -> None:
    run_command("coord", coord_command.run_lint)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
