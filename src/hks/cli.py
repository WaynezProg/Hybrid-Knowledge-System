"""Top-level Typer app for the HKS CLI."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from hks import __version__
from hks.commands import ingest as ingest_command
from hks.commands import lint as lint_command
from hks.commands import query as query_command
from hks.core.schema import QueryResponse, Route, build_error_response
from hks.errors import ExitCode, KSError

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


@app.command("lint")
def lint() -> None:
    run_command("lint", lint_command.run)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
