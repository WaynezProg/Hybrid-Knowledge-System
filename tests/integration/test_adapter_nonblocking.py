"""Adapters must keep the event loop responsive while core work runs."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import anyio
import httpx
import pytest
from mcp.types import CallToolResult

from hks.adapters import core
from hks.adapters.http_server import create_app
from hks.adapters.mcp_server import create_server


class _SlowCore:
    """Blocks inside the worker thread until the test releases it."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.released_by_test = False

    def __call__(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        self.started.set()
        # If the event loop were blocked, the test could never set `release`;
        # the bounded wait turns that deadlock into an assertion failure.
        self.released_by_test = self.release.wait(timeout=10)
        return {"answer": "slow", "source": [], "confidence": 0.0, "trace": {}}


async def _wait_thread_event(event: threading.Event) -> None:
    with anyio.fail_after(5):
        while not event.is_set():
            await anyio.sleep(0.01)


@pytest.mark.integration
def test_mcp_event_loop_stays_responsive_during_slow_tool(monkeypatch) -> None:
    slow = _SlowCore()
    monkeypatch.setattr(core, "hks_ingest", slow)
    server = create_server()

    async def scenario() -> None:
        results: list[Any] = []

        async def call_slow() -> None:
            results.append(await server.call_tool("hks_ingest", {"path": "/nowhere"}))

        async with anyio.create_task_group() as tg:
            tg.start_soon(call_slow)
            await _wait_thread_event(slow.started)
            # Loop is free: ticks, tools/list both complete while the tool runs.
            with anyio.fail_after(2):
                await anyio.sleep(0.05)
                tools = await server.list_tools()
            assert any(tool.name == "hks_ingest" for tool in tools)
            assert not results
            slow.release.set()
        assert results

    anyio.run(scenario)
    assert slow.released_by_test


@pytest.mark.integration
def test_mcp_cancellation_returns_promptly_and_skips_queued_call(monkeypatch) -> None:
    slow = _SlowCore()
    monkeypatch.setattr(core, "hks_ingest", slow)
    server = create_server()

    async def scenario() -> float:
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.call_tool, "hks_ingest", {"path": "/a"})
            await _wait_thread_event(slow.started)
            # Second call queues behind the process-wide core lock.
            tg.start_soon(server.call_tool, "hks_ingest", {"path": "/b"})
            await anyio.sleep(0.05)
            began = time.monotonic()
            tg.cancel_scope.cancel()
        return time.monotonic() - began

    elapsed = anyio.run(scenario)
    assert elapsed < 1.0
    slow.release.set()
    # Let the abandoned first call finish; the cancelled queued call never runs.
    time.sleep(0.2)
    assert slow.calls == 1


@pytest.mark.integration
def test_http_event_loop_stays_responsive_during_slow_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    slow = _SlowCore()
    monkeypatch.setattr(core, "hks_lint", slow)
    app = create_app()
    headers = {"host": "127.0.0.1", "authorization": "Bearer secret"}

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            responses: list[httpx.Response] = []

            async def call_slow() -> None:
                responses.append(await client.post("/lint", json={}, headers=headers))

            async with anyio.create_task_group() as tg:
                tg.start_soon(call_slow)
                await _wait_thread_event(slow.started)
                with anyio.fail_after(2):
                    rejected = await client.post("/lint", json={}, headers={"host": "127.0.0.1"})
                assert rejected.status_code == 401
                assert not responses
                slow.release.set()
            assert responses[0].status_code == 200

    anyio.run(scenario)
    assert slow.released_by_test


def _tool_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, CallToolResult):
        assert result.structuredContent is not None
        return dict(result.structuredContent)
    assert isinstance(result, list)
    return dict(json.loads(result[0].text))


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload["trace"]["steps"][0]["detail"])


@pytest.mark.integration
def test_mcp_light_calls_run_during_slow_exclusive_call(
    monkeypatch, working_docs, tmp_path
) -> None:
    core.hks_ingest(path=str(working_docs))
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(tmp_path / "workspaces.json"))
    slow = _SlowCore()
    monkeypatch.setattr(core, "hks_ingest", slow)
    server = create_server()

    async def scenario() -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.call_tool, "hks_ingest", {"path": "/nowhere"})
            await _wait_thread_event(slow.started)
            # The ingest holds the core lock; these must not queue behind it.
            with anyio.fail_after(5):
                claim = _tool_payload(
                    await server.call_tool(
                        "hks_coord_lease",
                        {"action": "claim", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
                    )
                )
                renew = _tool_payload(
                    await server.call_tool(
                        "hks_coord_lease",
                        {"action": "renew", "agent_id": "agent-a", "resource_key": "wiki:atlas"},
                    )
                )
                status = _tool_payload(await server.call_tool("hks_coord_status", {}))
                workspaces = _tool_payload(await server.call_tool("hks_workspace_list", {}))
                watch = _tool_payload(await server.call_tool("hks_watch_status", {}))
            assert not slow.release.is_set()
            assert _summary(claim)["leases"][0]["status"] == "active"
            assert _summary(renew)["operation"] == "lease.renew"
            assert [lease["resource_key"] for lease in _summary(status)["leases"]] == [
                "wiki:atlas"
            ]
            assert _summary(workspaces)["command"] == "workspace.list"
            assert _summary(watch)["operation"] == "status"
            slow.release.set()

    anyio.run(scenario)
    assert slow.released_by_test


@pytest.mark.integration
def test_mcp_exclusive_call_still_waits_for_slow_exclusive_call(monkeypatch) -> None:
    slow = _SlowCore()
    monkeypatch.setattr(core, "hks_ingest", slow)
    order: list[str] = []

    def quick_lint(**_: Any) -> dict[str, Any]:
        order.append("lint")
        return {"answer": "lint", "source": [], "confidence": 0.0, "trace": {}}

    monkeypatch.setattr(core, "hks_lint", quick_lint)
    server = create_server()

    async def scenario() -> None:
        async def call_slow() -> None:
            await server.call_tool("hks_ingest", {"path": "/nowhere"})
            order.append("ingest")

        async with anyio.create_task_group() as tg:
            tg.start_soon(call_slow)
            await _wait_thread_event(slow.started)
            tg.start_soon(server.call_tool, "hks_lint", {})
            await anyio.sleep(0.2)
            # Waits for the lock instead of running (or failing with LOCKED).
            assert order == []
            slow.release.set()

    anyio.run(scenario)
    assert slow.released_by_test
    assert sorted(order) == ["ingest", "lint"]


@pytest.mark.integration
def test_http_light_calls_run_during_slow_exclusive_endpoint(monkeypatch, working_docs) -> None:
    core.hks_ingest(path=str(working_docs))
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    slow = _SlowCore()
    monkeypatch.setattr(core, "hks_lint", slow)
    app = create_app()
    headers = {"host": "127.0.0.1", "authorization": "Bearer secret"}

    async def scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: client.post("/lint", json={}, headers=headers))
                await _wait_thread_event(slow.started)
                with anyio.fail_after(5):
                    lease = await client.post(
                        "/coord/lease",
                        json={
                            "action": "claim",
                            "agent_id": "agent-a",
                            "resource_key": "wiki:atlas",
                        },
                        headers=headers,
                    )
                    status = await client.post("/coord/status", json={}, headers=headers)
                    watch = await client.post("/watch/status", json={}, headers=headers)
                assert not slow.release.is_set()
                assert lease.status_code == 200
                assert status.status_code == 200
                assert watch.status_code == 200
                assert len(_summary(status.json())["leases"]) == 1
                slow.release.set()

    anyio.run(scenario)
    assert slow.released_by_test
