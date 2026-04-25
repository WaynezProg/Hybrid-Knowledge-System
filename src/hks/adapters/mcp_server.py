"""MCP server adapter for HKS."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

import typer
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from hks.adapters import core
from hks.adapters.models import AdapterToolError

app = typer.Typer(add_completion=False, no_args_is_help=False)


def _error_result(error: AdapterToolError) -> CallToolResult:
    envelope = error.to_dict()
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
        structuredContent=envelope,
        isError=True,
    )


def create_server() -> FastMCP:
    server = FastMCP("Hybrid Knowledge System", json_response=True)

    @server.tool()
    def hks_query(
        question: str,
        writeback: str = "no",
        ks_root: str | None = None,
    ) -> Any:
        """Query the local HKS knowledge base."""
        try:
            return core.hks_query(question=question, writeback=writeback, ks_root=ks_root)
        except AdapterToolError as error:
            return _error_result(error)

    @server.tool()
    def hks_ingest(
        path: str,
        prune: bool = False,
        pptx_notes: str = "include",
        ks_root: str | None = None,
    ) -> Any:
        """Ingest a local file or directory into HKS."""
        try:
            return core.hks_ingest(
                path=path,
                prune=prune,
                pptx_notes=pptx_notes,
                ks_root=ks_root,
            )
        except AdapterToolError as error:
            return _error_result(error)

    @server.tool()
    def hks_lint(
        strict: bool = False,
        severity_threshold: str = "error",
        fix: str = "none",
        ks_root: str | None = None,
    ) -> Any:
        """Check HKS runtime consistency."""
        try:
            return core.hks_lint(
                strict=strict,
                severity_threshold=severity_threshold,
                fix=fix,
                ks_root=ks_root,
            )
        except AdapterToolError as error:
            return _error_result(error)

    return server


def _validate_host(host: str, *, allow_non_loopback: bool) -> None:
    if allow_non_loopback:
        return
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter(
            "non-loopback host requires --allow-non-loopback",
            param_hint="--host",
        )


@app.callback(invoke_without_command=True)
def run(
    transport: Annotated[
        Literal["stdio", "streamable-http"],
        typer.Option("--transport", help="MCP transport."),
    ] = "stdio",
    host: Annotated[str, typer.Option("--host", help="Host for streamable-http.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port for streamable-http.")] = 8765,
    allow_non_loopback: Annotated[
        bool,
        typer.Option("--allow-non-loopback", help="Allow binding non-loopback host."),
    ] = False,
) -> None:
    _validate_host(host, allow_non_loopback=allow_non_loopback)
    server = create_server()
    server.settings.host = host
    server.settings.port = port
    server.run(transport=transport)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
