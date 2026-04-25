"""Top-level Typer app for the HKS CLI."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn, cast

import typer

from hks import __version__
from hks.commands import ingest as ingest_command
from hks.commands import lint as lint_command
from hks.commands import query as query_command
from hks.core.schema import QueryResponse, Route, build_error_response
from hks.errors import ExitCode, KSError
from hks.lint.models import FixMode, SeverityThreshold

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)


class WritebackMode(StrEnum):
    auto = "auto"
    yes = "yes"
    no = "no"
    ask = "ask"


class PptxNotesMode(StrEnum):
    include = "include"
    exclude = "exclude"


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
