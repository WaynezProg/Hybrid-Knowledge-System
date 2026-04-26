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

    @server.tool()
    def hks_llm_classify(
        source_relpath: str,
        mode: str = "preview",
        provider: str = "fake",
        model: str | None = None,
        prompt_version: str | None = None,
        force_new_run: bool = False,
        requested_by: str | None = None,
        ks_root: str | None = None,
    ) -> Any:
        """Run LLM-assisted classification/extraction for one ingested source."""
        try:
            return core.hks_llm_classify(
                source_relpath=source_relpath,
                mode=mode,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                force_new_run=force_new_run,
                requested_by=requested_by,
                ks_root=ks_root,
            )
        except AdapterToolError as error:
            return _error_result(error)

    @server.tool()
    def hks_coord_session(
        action: str,
        agent_id: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ks_root: str | None = None,
    ) -> Any:
        """Start, heartbeat, or close a coordination session."""
        try:
            return core.hks_coord_session(
                action=action,
                agent_id=agent_id,
                session_id=session_id,
                metadata=metadata,
                ks_root=ks_root,
            )
        except AdapterToolError as error:
            return _error_result(error)

    @server.tool()
    def hks_coord_lease(
        action: str,
        agent_id: str,
        resource_key: str,
        session_id: str | None = None,
        lease_id: str | None = None,
        ttl_seconds: int = 1800,
        reason: str | None = None,
        ks_root: str | None = None,
    ) -> Any:
        """Claim, renew, or release a coordination lease."""
        try:
            return core.hks_coord_lease(
                action=action,
                agent_id=agent_id,
                resource_key=resource_key,
                session_id=session_id,
                lease_id=lease_id,
                ttl_seconds=ttl_seconds,
                reason=reason,
                ks_root=ks_root,
            )
        except AdapterToolError as error:
            return _error_result(error)

    @server.tool()
    def hks_coord_handoff(
        action: str,
        agent_id: str,
        resource_key: str | None = None,
        summary: str | None = None,
        next_action: str | None = None,
        references: list[dict[str, Any]] | None = None,
        blocked_by: list[str] | None = None,
        ks_root: str | None = None,
    ) -> Any:
        """Add or list coordination handoff notes."""
        try:
            return core.hks_coord_handoff(
                action=action,
                agent_id=agent_id,
                resource_key=resource_key,
                summary=summary,
                next_action=next_action,
                references=references,
                blocked_by=blocked_by,
                ks_root=ks_root,
            )
        except AdapterToolError as error:
            return _error_result(error)

    @server.tool()
    def hks_coord_status(
        agent_id: str | None = None,
        resource_key: str | None = None,
        include_stale: bool = True,
        ks_root: str | None = None,
    ) -> Any:
        """Return coordination sessions, leases, and handoffs."""
        try:
            return core.hks_coord_status(
                agent_id=agent_id,
                resource_key=resource_key,
                include_stale=include_stale,
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
