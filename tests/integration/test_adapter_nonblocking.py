"""Adapters must keep the event loop responsive while core work runs."""

from __future__ import annotations

import threading
import time
from typing import Any

import anyio
import httpx
import pytest

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
