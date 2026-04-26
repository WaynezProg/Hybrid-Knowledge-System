"""Optional loopback HTTP facade over the shared adapter core."""

from __future__ import annotations

from typing import Annotated, Any

import typer
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hks.adapters import core
from hks.adapters.models import AdapterToolError

app = typer.Typer(add_completion=False, no_args_is_help=False)


async def _json(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _response(callable_: Any, **kwargs: Any) -> JSONResponse:
    try:
        return JSONResponse(callable_(**kwargs))
    except AdapterToolError as error:
        status = 400 if error.error.exit_code in {2, 65, 66} else 500
        return JSONResponse(error.to_dict(), status_code=status)
    except Exception as error:
        return JSONResponse(
            {
                "ok": False,
                "error": {
                    "code": type(error).__name__.upper(),
                    "exit_code": 1,
                    "message": str(error),
                    "details": [],
                },
                "response": None,
            },
            status_code=500,
        )


def _usage_response(message: str) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": "USAGE",
                "exit_code": 2,
                "message": message,
                "details": [],
            },
            "response": None,
        },
        status_code=400,
    )


async def _adapter_response(request: Request, callable_: Any) -> JSONResponse:
    try:
        payload = await _json(request)
    except Exception as error:
        return _usage_response(str(error))
    return _response(callable_, **payload)


async def query_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_query)


async def ingest_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_ingest)


async def lint_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_lint)


async def llm_classify_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_llm_classify)


async def wiki_synthesize_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_wiki_synthesize)


async def graphify_build_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_graphify_build)


async def watch_scan_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_watch_scan)


async def watch_run_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_watch_run)


async def watch_status_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_watch_status)


async def coord_session_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_coord_session)


async def coord_lease_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_coord_lease)


async def coord_handoff_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_coord_handoff)


async def coord_status_endpoint(request: Request) -> Response:
    return await _adapter_response(request, core.hks_coord_status)


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/query", query_endpoint, methods=["POST"]),
            Route("/ingest", ingest_endpoint, methods=["POST"]),
            Route("/lint", lint_endpoint, methods=["POST"]),
            Route("/llm/classify", llm_classify_endpoint, methods=["POST"]),
            Route("/wiki/synthesize", wiki_synthesize_endpoint, methods=["POST"]),
            Route("/graphify/build", graphify_build_endpoint, methods=["POST"]),
            Route("/watch/scan", watch_scan_endpoint, methods=["POST"]),
            Route("/watch/run", watch_run_endpoint, methods=["POST"]),
            Route("/watch/status", watch_status_endpoint, methods=["POST"]),
            Route("/coord/session", coord_session_endpoint, methods=["POST"]),
            Route("/coord/lease", coord_lease_endpoint, methods=["POST"]),
            Route("/coord/handoff", coord_handoff_endpoint, methods=["POST"]),
            Route("/coord/status", coord_status_endpoint, methods=["POST"]),
        ]
    )


def _validate_host(host: str, *, allow_non_loopback: bool) -> None:
    if allow_non_loopback:
        return
    if host not in {"127.0.0.1", "localhost", "::1"}:
        typer.echo(
            "Error: --host: non-loopback host requires --allow-non-loopback",
            err=True,
        )
        raise typer.Exit(code=2)


@app.callback(invoke_without_command=True)
def run(
    host: Annotated[str, typer.Option("--host", help="HTTP host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="HTTP port.")] = 8766,
    allow_non_loopback: Annotated[
        bool,
        typer.Option("--allow-non-loopback", help="Allow binding non-loopback host."),
    ] = False,
) -> None:
    _validate_host(host, allow_non_loopback=allow_non_loopback)
    uvicorn.run(create_app(), host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
