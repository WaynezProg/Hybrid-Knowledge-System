# 014 Runtime Isolation Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make adapter-scoped `KS_ROOT` request-local and protect the optional HTTP facade from unauthenticated mutation, browser-origin requests, host-header abuse, and arbitrary ingest paths.

**Architecture:** Add one shared runtime context module used by adapters and workspace query, then make `resolve_ks_root()` prefer explicit root, context root, config/env, and cwd fallback in that order. Add Starlette middleware plus a small HTTP ingest resolver so security is centralized in the HTTP layer while CLI and MCP keep their local-tool semantics.

**Tech Stack:** Python 3.12, contextvars, Starlette middleware, existing Typer/FastMCP adapter core, existing HKS config loader.

**Spec:** `docs/superpowers/specs/2026-05-21-runtime-safety-and-retrieval-quality-design.md`

---

## File Map

### New Files

| File | Responsibility |
|------|----------------|
| `src/hks/core/runtime_context.py` | Request-local `KS_ROOT` contextvar and context manager |
| `src/hks/adapters/http_security.py` | HTTP Host/auth/browser guard and HTTP ingest path resolver |
| `tests/unit/core/test_runtime_context.py` | Runtime context precedence and restore tests |
| `tests/integration/test_adapter_runtime_context.py` | Adapter/workspace isolation tests |
| `tests/integration/test_http_security.py` | HTTP Host/auth/browser middleware tests |
| `tests/integration/test_http_ingest_allowlist.py` | HTTP ingest allowed-root, absolute path, symlink escape, hidden-dir tests |

### Modified Files

| File | Change |
|------|--------|
| `src/hks/core/paths.py` | Read `current_ks_root` before config/env |
| `src/hks/core/config.py` | Add `HKS_API_*` env mappings |
| `src/hks/adapters/core.py` | Remove local env-mutating `scoped_ks_root`; import shared context manager |
| `src/hks/workspace/service.py` | Remove local env-mutating `scoped_ks_root`; import shared context manager |
| `src/hks/adapters/http_server.py` | Install HTTP security middleware and HTTP-only ingest path resolution |
| `src/hks/commands/ingest.py` | Accept internal `skip_dir_names` kwarg for HTTP-safe directory ingest |
| `src/hks/ingest/pipeline.py` | Add optional directory-prune behavior to `discover_files()` |
| `tests/unit/adapters/test_core.py` | Update scoped-root test so env is not mutated |
| `tests/integration/test_http_adapter.py` | Add Host header and token/ingest-root setup for mutating endpoint |
| `tests/integration/test_catalog_http.py` | Add Host header/token for workspace register |
| `mcp/http.md` | Document token, host, browser, and ingest-root rules |
| `docs/configuration.md` | Document new `HKS_API_*` settings |

---

## Task 1: Runtime Context Module

**Files:**
- Create: `src/hks/core/runtime_context.py`
- Modify: `src/hks/core/paths.py`
- Create: `tests/unit/core/test_runtime_context.py`

- [ ] **Step 1: Write failing runtime context tests**

Create `tests/unit/core/test_runtime_context.py`:

```python
from __future__ import annotations

from pathlib import Path

from hks.core.paths import resolve_ks_root, runtime_paths
from hks.core.runtime_context import current_ks_root, scoped_ks_root


def test_scoped_ks_root_overrides_env_and_restores(monkeypatch, tmp_path: Path) -> None:
    env_root = tmp_path / "env-ks"
    scoped_root = tmp_path / "scoped-ks"
    monkeypatch.setenv("KS_ROOT", str(env_root))

    assert resolve_ks_root() == env_root.resolve(strict=False)
    assert current_ks_root() is None

    with scoped_ks_root(scoped_root):
        assert current_ks_root() == scoped_root.resolve(strict=False)
        assert resolve_ks_root() == scoped_root.resolve(strict=False)
        assert runtime_paths().root == scoped_root.resolve(strict=False)

    assert current_ks_root() is None
    assert resolve_ks_root() == env_root.resolve(strict=False)


def test_explicit_root_beats_context_root(tmp_path: Path) -> None:
    scoped_root = tmp_path / "scoped-ks"
    explicit_root = tmp_path / "explicit-ks"

    with scoped_ks_root(scoped_root):
        assert resolve_ks_root(explicit_root) == explicit_root.resolve(strict=False)
        assert runtime_paths(explicit_root).root == explicit_root.resolve(strict=False)


def test_nested_scopes_restore_outer_root(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = tmp_path / "inner"

    with scoped_ks_root(outer):
        assert resolve_ks_root() == outer.resolve(strict=False)
        with scoped_ks_root(inner):
            assert resolve_ks_root() == inner.resolve(strict=False)
        assert resolve_ks_root() == outer.resolve(strict=False)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/core/test_runtime_context.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'hks.core.runtime_context'`.

- [ ] **Step 3: Add the runtime context module**

Create `src/hks/core/runtime_context.py`:

```python
"""Request-local runtime context for HKS adapters."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_CURRENT_KS_ROOT: ContextVar[Path | None] = ContextVar("hks_current_ks_root", default=None)


def current_ks_root() -> Path | None:
    """Return the current request-scoped runtime root, if one is active."""

    return _CURRENT_KS_ROOT.get()


@contextmanager
def scoped_ks_root(ks_root: str | Path | None) -> Iterator[None]:
    """Set a request-local KS_ROOT without mutating process environment."""

    if ks_root is None:
        yield
        return

    resolved = Path(ks_root).expanduser().resolve(strict=False)
    token = _CURRENT_KS_ROOT.set(resolved)
    try:
        yield
    finally:
        _CURRENT_KS_ROOT.reset(token)
```

- [ ] **Step 4: Wire `resolve_ks_root()` to the contextvar**

In `src/hks/core/paths.py`, add the import and context precedence:

```python
from hks.core.config import config_value
from hks.core.runtime_context import current_ks_root
```

Replace `resolve_ks_root()` with:

```python
def resolve_ks_root(root: Path | str | None = None) -> Path:
    """Resolve the runtime root, defaulting to ./ks in the current workspace."""

    if root is not None:
        return Path(root).expanduser().resolve(strict=False)

    scoped_root = current_ks_root()
    if scoped_root is not None:
        return scoped_root

    env_root = config_value("KS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve(strict=False)

    return (Path.cwd() / "ks").resolve(strict=False)
```

- [ ] **Step 5: Remove module-level path constants from `paths.py`**

`src/hks/core/paths.py` currently ends with:

```python
_DEFAULT_PATHS = runtime_paths()

KS_ROOT = _DEFAULT_PATHS.root
RAW_SOURCES_DIR = _DEFAULT_PATHS.raw_sources
WIKI_DIR = _DEFAULT_PATHS.wiki
WIKI_PAGES_DIR = _DEFAULT_PATHS.wiki_pages
PAGE_TREES_DIR = _DEFAULT_PATHS.page_trees
GRAPH_DIR = _DEFAULT_PATHS.graph_dir
GRAPH_FILE = _DEFAULT_PATHS.graph_file
VECTOR_DB_DIR = _DEFAULT_PATHS.vector_db
MANIFEST_PATH = _DEFAULT_PATHS.manifest
LOCK_PATH = _DEFAULT_PATHS.lock
```

These are evaluated at import-time and are process-global. Any code that imported them directly would bypass the contextvar entirely. Delete all 12 lines. Verified: no module in `src/` or `tests/` imports these constants — they are safe to remove.

- [ ] **Step 6: Run runtime context tests**

Run: `uv run pytest tests/unit/core/test_runtime_context.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hks/core/runtime_context.py src/hks/core/paths.py tests/unit/core/test_runtime_context.py
git commit -m "feat(runtime): add request-scoped ks root context"
```

---

## Task 2: Adapter Core Uses Contextvar

**Files:**
- Modify: `src/hks/adapters/core.py`
- Modify: `tests/unit/adapters/test_core.py`

- [ ] **Step 1: Update adapter core tests**

In `tests/unit/adapters/test_core.py`, replace `test_scoped_ks_root_restores_environment` with:

```python
def test_hks_query_uses_scoped_ks_root_without_mutating_environment(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("KS_ROOT", "/existing/root")
    scoped_root = tmp_path / "custom"

    def fake_run(question: str, *, writeback: str) -> QueryResponse:
        from hks.core.paths import runtime_paths

        assert question == "Project Atlas"
        assert writeback == "no"
        assert runtime_paths().root == scoped_root.resolve(strict=False)
        assert core.os.environ["KS_ROOT"] == "/existing/root"
        return _response()

    monkeypatch.setattr(core.query_command, "run", fake_run)

    payload = core.hks_query(question="Project Atlas", ks_root=str(scoped_root))

    assert payload["answer"] == "Atlas summary"
    assert core.os.environ["KS_ROOT"] == "/existing/root"
    # scoped root must NOT appear in process environment
    assert str(scoped_root.resolve(strict=False)) not in core.os.environ.get("KS_ROOT", "")
```

- [ ] **Step 2: Run the updated adapter test to verify it fails**

Run: `uv run pytest tests/unit/adapters/test_core.py::test_hks_query_uses_scoped_ks_root_without_mutating_environment -q`

Expected: FAIL because `core.scoped_ks_root()` still mutates `os.environ`.

- [ ] **Step 3: Remove local env mutation from adapter core**

In `src/hks/adapters/core.py`, remove these imports if unused:

```python
from collections.abc import Iterator
from contextlib import contextmanager
```

Add this import:

```python
from hks.core.runtime_context import scoped_ks_root
```

Delete the local `scoped_ks_root()` function from `src/hks/adapters/core.py`. Keep `_run_command()` as:

```python
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
```

- [ ] **Step 4: Run adapter tests**

Run: `uv run pytest tests/unit/adapters/test_core.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hks/adapters/core.py tests/unit/adapters/test_core.py
git commit -m "fix(adapter): scope ks root without mutating environment"
```

---

## Task 3: Workspace Query Uses Shared Runtime Context

**Files:**
- Modify: `src/hks/workspace/service.py`
- Create: `tests/integration/test_adapter_runtime_context.py`

- [ ] **Step 1: Write workspace no-env-mutation test**

Create `tests/integration/test_adapter_runtime_context.py`:

```python
from __future__ import annotations

import anyio
import pytest

from hks.adapters import core
from hks.commands import query as query_command
from hks.core.paths import runtime_paths
from hks.core.schema import QueryResponse, Trace
from hks.workspace import service as workspace_service


def _response(label: str) -> QueryResponse:
    return QueryResponse(
        answer=label,
        source=["wiki"],
        confidence=1.0,
        trace=Trace(route="wiki", steps=[]),
    )


def test_workspace_query_uses_context_without_env_mutation(monkeypatch, tmp_path) -> None:
    registry_path = tmp_path / "workspaces.json"
    ks_root = tmp_path / "workspace-ks"
    monkeypatch.setenv("KS_ROOT", "/existing/root")
    workspace_service.register_workspace(
        workspace_id="proj-a",
        ks_root=ks_root,
        registry_path_value=registry_path,
    )

    def fake_query(question: str, *, writeback: str) -> QueryResponse:
        assert runtime_paths().root == ks_root.resolve(strict=False)
        assert question == "Atlas"
        assert writeback == "no"
        return _response("Atlas")

    monkeypatch.setattr(query_command, "run", fake_query)

    payload = workspace_service.query_workspace(
        "proj-a",
        "Atlas",
        writeback="no",
        registry_path_value=registry_path,
    )

    assert payload.answer == "Atlas"
    assert core.os.environ["KS_ROOT"] == "/existing/root"


@pytest.mark.integration
def test_parallel_adapter_queries_keep_distinct_roots(monkeypatch, tmp_path) -> None:
    """Verify contextvar isolation under true OS-thread concurrency.

    Uses ThreadPoolExecutor so both calls run simultaneously in separate threads.
    Each thread gets its own contextvar copy via run_in_executor's context
    propagation, so they cannot overwrite each other's KS_ROOT.
    anyio.gather does not exist in this project's anyio version, and async task
    groups run coroutines sequentially (no true concurrency for sync code).
    ThreadPoolExecutor is the correct tool to stress-test the contextvar boundary.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    first_root = tmp_path / "first-ks"
    second_root = tmp_path / "second-ks"
    seen: dict[str, str] = {}

    def fake_query(q: str, *, writeback: str) -> QueryResponse:
        seen[q] = runtime_paths().root.as_posix()
        return _response(q)

    monkeypatch.setattr(query_command, "run", fake_query)

    async def run_both() -> tuple[dict, dict]:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = loop.run_in_executor(
                pool, lambda: core.hks_query(question="first", writeback="no", ks_root=str(first_root))
            )
            f2 = loop.run_in_executor(
                pool, lambda: core.hks_query(question="second", writeback="no", ks_root=str(second_root))
            )
            return await asyncio.gather(f1, f2)

    first, second = anyio.run(run_both)

    assert first["answer"] == "first"
    assert second["answer"] == "second"
    assert seen.get("first") == first_root.resolve(strict=False).as_posix()
    assert seen.get("second") == second_root.resolve(strict=False).as_posix()
```

- [ ] **Step 2: Run workspace test to verify it fails**

Run: `uv run pytest tests/integration/test_adapter_runtime_context.py::test_workspace_query_uses_context_without_env_mutation -q`

Expected: FAIL because `workspace/service.py` still mutates `os.environ`.

- [ ] **Step 3: Update workspace service**

In `src/hks/workspace/service.py`, remove:

```python
import os
from collections.abc import Iterator
from contextlib import contextmanager
```

Add:

```python
from hks.core.runtime_context import scoped_ks_root
```

Delete the local `scoped_ks_root()` function. Keep `query_workspace()` using:

```python
with scoped_ks_root(record.ks_root):
    return query_command.run(question, writeback=writeback)
```

- [ ] **Step 4: Run runtime context integration tests**

Run: `uv run pytest tests/integration/test_adapter_runtime_context.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/hks/workspace/service.py tests/integration/test_adapter_runtime_context.py
git commit -m "fix(workspace): query selected roots with runtime context"
```

---

## Task 4: HTTP Security Middleware

**Files:**
- Modify: `src/hks/core/config.py`
- Create: `src/hks/adapters/http_security.py`
- Modify: `src/hks/adapters/http_server.py`
- Create: `tests/integration/test_http_security.py`

- [ ] **Step 1: Add failing HTTP security tests**

Create `tests/integration/test_http_security.py`:

```python
from __future__ import annotations

from starlette.testclient import TestClient

from hks.adapters.http_server import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def _host_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if extra:
        headers.update(extra)
    return headers


def test_rejects_invalid_host_header() -> None:
    response = _client().post("/lint", headers={"host": "evil.example"}, json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_HOST_FORBIDDEN"


def test_mutating_endpoint_requires_token_configuration(monkeypatch) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)

    response = _client().post("/ingest", headers=_host_headers(), json={"path": "a.md"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_MUTATION_TOKEN_NOT_CONFIGURED"


def test_mutating_endpoint_rejects_missing_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")

    response = _client().post("/ingest", headers=_host_headers(), json={"path": "a.md"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HTTP_AUTH_REQUIRED"


def test_mutating_endpoint_rejects_wrong_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")

    response = _client().post(
        "/ingest",
        headers=_host_headers({"authorization": "Bearer wrong"}),
        json={"path": "a.md"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HTTP_AUTH_REQUIRED"


def test_browser_style_mutating_request_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")

    response = _client().post(
        "/ingest",
        headers=_host_headers(
            {
                "authorization": "Bearer secret",
                "origin": "https://attacker.example",
            }
        ),
        json={"path": "a.md"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_BROWSER_REQUEST_FORBIDDEN"


def test_read_only_endpoint_does_not_require_token(monkeypatch) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)

    response = _client().post("/lint", headers=_host_headers(), json={})

    assert response.status_code != 401
    assert response.status_code != 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_security.py -q`

Expected: FAIL because `http_security.py` and middleware do not exist.

- [ ] **Step 3: Add `HKS_API_*` config mappings**

In `src/hks/core/config.py`, add to `_KNOWN_ENV_PATHS`:

```python
    "HKS_API_TOKEN": ("api", "token"),
    "HKS_API_HOST_ALLOWLIST": ("api", "host_allowlist"),
    "HKS_API_REJECT_BROWSER_REQUESTS": ("api", "reject_browser_requests"),
    "HKS_API_INGEST_ROOTS": ("api", "ingest_roots"),
```

- [ ] **Step 4: Implement HTTP security helpers**

Create `src/hks/adapters/http_security.py`:

```python
"""HTTP-only security guards for the optional HKS API facade."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hks.core.config import config_value
from hks.errors import ExitCode

DEFAULT_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
BLOCKED_INGEST_SEGMENTS = frozenset({".git", ".ssh", ".env", "node_modules", ".venv", "__pycache__"})


@dataclass(frozen=True, slots=True)
class HttpSecurityFailure(Exception):
    status_code: int
    code: str
    message: str


def security_error_response(failure: HttpSecurityFailure) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": {
                "code": failure.code,
                "exit_code": int(ExitCode.USAGE),
                "message": failure.message,
                "details": [],
            },
            "response": None,
        },
        status_code=failure.status_code,
    )


def _host_name(host_header: str) -> str:
    host = host_header.strip()
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    if ":" in host:
        return host.rsplit(":", 1)[0]
    return host


def _allowed_hosts() -> set[str]:
    raw = config_value("HKS_API_HOST_ALLOWLIST")
    if not raw:
        return set(DEFAULT_HOSTS)
    return {part.strip() for part in raw.split(",") if part.strip()}


def _reject_browser_requests() -> bool:
    raw = (config_value("HKS_API_REJECT_BROWSER_REQUESTS") or "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def is_mutating_request(request: Request) -> bool:
    """Return True if this request targets a mutating endpoint.

    /workspaces and /workspaces/{id} are treated as always-mutating regardless
    of the action field in the body. This avoids consuming the request body in
    middleware (which could interact with Starlette's body-caching) and closes
    a gap where a malformed JSON body would default to 'list'/'show' and bypass
    auth before hitting the endpoint's own parse error.
    """
    path = request.url.path
    method = request.method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    if path in {
        "/ingest",
        "/llm/classify",
        "/wiki/synthesize",
        "/graphify/build",
        "/watch/run",
        "/coord/session",
        "/coord/lease",
        "/coord/handoff",
    }:
        return True
    if path == "/workspaces" or path.startswith("/workspaces/"):
        return True
    return False


async def guard_http_request(request: Request) -> HttpSecurityFailure | None:
    host = _host_name(request.headers.get("host", ""))
    if host not in _allowed_hosts():
        return HttpSecurityFailure(400, "HTTP_HOST_FORBIDDEN", "Host header is not allowed")

    mutating = is_mutating_request(request)
    if not mutating:
        return None

    if _reject_browser_requests() and (
        request.headers.get("origin") or request.headers.get("sec-fetch-site")
    ):
        return HttpSecurityFailure(
            403,
            "HTTP_BROWSER_REQUEST_FORBIDDEN",
            "Browser-origin mutating requests are rejected",
        )

    token = config_value("HKS_API_TOKEN")
    if not token:
        return HttpSecurityFailure(
            403,
            "HTTP_MUTATION_TOKEN_NOT_CONFIGURED",
            "HKS_API_TOKEN is required before mutating HTTP endpoints are enabled",
        )

    expected = f"Bearer {token}"
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied, expected):
        return HttpSecurityFailure(401, "HTTP_AUTH_REQUIRED", "Bearer token is required")

    return None


async def http_security_dispatch(request: Request, call_next) -> Response:
    failure = await guard_http_request(request)
    if failure is not None:
        return security_error_response(failure)
    return await call_next(request)
```

- [ ] **Step 5: Install middleware in `create_app()`**

In `src/hks/adapters/http_server.py`, add imports:

```python
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from hks.adapters.http_security import http_security_dispatch
```

Update `create_app()`:

```python
def create_app() -> Starlette:
    return Starlette(
        middleware=[Middleware(BaseHTTPMiddleware, dispatch=http_security_dispatch)],
        routes=[
            Route("/query", query_endpoint, methods=["POST"]),
            Route("/ingest", ingest_endpoint, methods=["POST"]),
            Route("/lint", lint_endpoint, methods=["POST"]),
            Route("/pageindex/enrich", pageindex_enrich_endpoint, methods=["POST"]),
            Route("/pageindex/{relpath:path}", pageindex_show_endpoint, methods=["GET"]),
            Route("/llm/classify", llm_classify_endpoint, methods=["POST"]),
            Route("/wiki/synthesize", wiki_synthesize_endpoint, methods=["POST"]),
            Route("/graphify/build", graphify_build_endpoint, methods=["POST"]),
            Route("/watch/scan", watch_scan_endpoint, methods=["POST"]),
            Route("/watch/run", watch_run_endpoint, methods=["POST"]),
            Route("/watch/status", watch_status_endpoint, methods=["POST"]),
            Route("/catalog/sources", source_list_endpoint, methods=["POST"]),
            Route("/catalog/sources/{relpath:path}", source_show_endpoint, methods=["POST"]),
            Route("/workspaces", workspaces_endpoint, methods=["POST"]),
            Route("/workspaces/{workspace_id}", workspace_endpoint, methods=["POST"]),
            Route("/workspaces/{workspace_id}/query", workspace_query_endpoint, methods=["POST"]),
            Route("/coord/session", coord_session_endpoint, methods=["POST"]),
            Route("/coord/lease", coord_lease_endpoint, methods=["POST"]),
            Route("/coord/handoff", coord_handoff_endpoint, methods=["POST"]),
            Route("/coord/status", coord_status_endpoint, methods=["POST"]),
        ],
    )
```

- [ ] **Step 6: Run HTTP security tests**

Run: `uv run pytest tests/integration/test_http_security.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/hks/core/config.py src/hks/adapters/http_security.py src/hks/adapters/http_server.py tests/integration/test_http_security.py
git commit -m "feat(http): add host auth and browser request guards"
```

---

## Task 5: HTTP Ingest Allowlist

**Files:**
- Modify: `src/hks/adapters/http_security.py`
- Modify: `src/hks/adapters/http_server.py`
- Modify: `src/hks/commands/ingest.py`
- Modify: `src/hks/ingest/pipeline.py`
- Create: `tests/integration/test_http_ingest_allowlist.py`

- [ ] **Step 1: Write failing HTTP ingest allowlist tests**

Create `tests/integration/test_http_ingest_allowlist.py`:

```python
from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from hks.adapters.http_server import create_app
from hks.core.manifest import load_manifest


def _headers() -> dict[str, str]:
    return {"host": "127.0.0.1", "authorization": "Bearer secret"}


def _configure(monkeypatch, source_root: Path) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    monkeypatch.setenv("HKS_API_INGEST_ROOTS", f"docs={source_root}")


def test_http_ingest_accepts_relative_path_under_allowed_root(monkeypatch, tmp_path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    (source_root / "atlas.md").write_text("Atlas owns checkout service.", encoding="utf-8")
    ks_root = tmp_path / "ks"
    _configure(monkeypatch, source_root)

    response = TestClient(create_app()).post(
        "/ingest",
        headers=_headers(),
        json={"ks_root": str(ks_root), "source_root_id": "docs", "path": "atlas.md"},
    )

    assert response.status_code == 200
    assert "atlas.md" in load_manifest(ks_root / "manifest.json").entries


def test_http_ingest_rejects_absolute_path(monkeypatch, tmp_path) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    _configure(monkeypatch, source_root)

    response = TestClient(create_app()).post(
        "/ingest",
        headers=_headers(),
        json={"ks_root": str(tmp_path / "ks"), "source_root_id": "docs", "path": str(source_root)},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_PATH_FORBIDDEN"


def test_http_ingest_rejects_symlink_escape(monkeypatch, tmp_path) -> None:
    source_root = tmp_path / "sources"
    outside = tmp_path / "outside"
    source_root.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_text("secret", encoding="utf-8")
    (source_root / "link.md").symlink_to(outside / "secret.md")
    _configure(monkeypatch, source_root)

    response = TestClient(create_app()).post(
        "/ingest",
        headers=_headers(),
        json={"ks_root": str(tmp_path / "ks"), "source_root_id": "docs", "path": "link.md"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HTTP_INGEST_PATH_FORBIDDEN"


def test_http_ingest_skips_blocked_dirs(monkeypatch, tmp_path) -> None:
    source_root = tmp_path / "sources"
    docs = source_root / "docs"
    docs.mkdir(parents=True)
    (docs / "visible.md").write_text("Visible Atlas note.", encoding="utf-8")
    hidden = docs / ".ssh"
    hidden.mkdir()
    (hidden / "secret.md").write_text("Hidden secret note.", encoding="utf-8")
    ks_root = tmp_path / "ks"
    _configure(monkeypatch, source_root)

    response = TestClient(create_app()).post(
        "/ingest",
        headers=_headers(),
        json={"ks_root": str(ks_root), "source_root_id": "docs", "path": "docs"},
    )

    assert response.status_code == 200
    entries = load_manifest(ks_root / "manifest.json").entries
    assert "visible.md" in entries or "docs/visible.md" in entries
    assert all("secret.md" not in relpath for relpath in entries)


def test_http_ingest_without_allowed_roots_is_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    monkeypatch.delenv("HKS_API_INGEST_ROOTS", raising=False)

    response = TestClient(create_app()).post(
        "/ingest",
        headers=_headers(),
        json={"ks_root": str(tmp_path / "ks"), "path": "atlas.md"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HTTP_INGEST_ROOTS_NOT_CONFIGURED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_http_ingest_allowlist.py -q`

Expected: FAIL because `/ingest` still passes raw `path` to adapter core.

- [ ] **Step 3: Add ingest-root parsing and path resolution**

Append to `src/hks/adapters/http_security.py`:

```python
def parse_ingest_roots() -> dict[str, Path]:
    raw = config_value("HKS_API_INGEST_ROOTS")
    if not raw:
        return {}
    roots: dict[str, Path] = {}
    for item in raw.split(","):
        part = item.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        root_id, root_path = part.split("=", 1)
        root_id = root_id.strip()
        if root_id:
            roots[root_id] = Path(root_path.strip()).expanduser().resolve(strict=False)
    return roots


def resolve_http_ingest_path(path: str, *, source_root_id: str | None = None) -> Path:
    roots = parse_ingest_roots()
    if not roots:
        raise HttpSecurityFailure(
            403,
            "HTTP_INGEST_ROOTS_NOT_CONFIGURED",
            "HKS_API_INGEST_ROOTS must be configured before HTTP ingest is enabled",
        )
    if source_root_id is None:
        if len(roots) != 1:
            raise HttpSecurityFailure(
                400,
                "HTTP_INGEST_SOURCE_ROOT_REQUIRED",
                "source_root_id is required when multiple ingest roots are configured",
            )
        root = next(iter(roots.values()))
    else:
        root = roots.get(source_root_id)
        if root is None:
            raise HttpSecurityFailure(
                400,
                "HTTP_INGEST_SOURCE_ROOT_UNKNOWN",
                f"unknown source_root_id: {source_root_id}",
            )

    candidate = Path(path)
    if candidate.is_absolute():
        raise HttpSecurityFailure(400, "HTTP_INGEST_PATH_FORBIDDEN", "absolute ingest paths are forbidden")
    if any(part in BLOCKED_INGEST_SEGMENTS for part in candidate.parts):
        raise HttpSecurityFailure(400, "HTTP_INGEST_PATH_FORBIDDEN", "blocked ingest path segment")

    resolved = (root / candidate).resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise HttpSecurityFailure(400, "HTTP_INGEST_PATH_FORBIDDEN", "ingest path escapes allowed root")
    return resolved
```

- [ ] **Step 4: Apply HTTP-only path resolution in `/ingest`**

In `src/hks/adapters/http_server.py`, import:

```python
from hks.adapters.http_security import (
    BLOCKED_INGEST_SEGMENTS,
    HttpSecurityFailure,
    http_security_dispatch,
    resolve_http_ingest_path,
    security_error_response,
)
```

Replace `ingest_endpoint()`:

```python
async def ingest_endpoint(request: Request) -> Response:
    try:
        payload = await _json(request)
        source_root_id = payload.pop("source_root_id", None)
        if source_root_id is not None and not isinstance(source_root_id, str):
            return _usage_response("source_root_id must be a string")
        path = payload.get("path")
        if not isinstance(path, str):
            return _usage_response("path must be a string")
        payload["path"] = resolve_http_ingest_path(path, source_root_id=source_root_id).as_posix()
    except HttpSecurityFailure as failure:
        return security_error_response(failure)
    except Exception as error:
        return _usage_response(str(error))
    return _response(
        core.hks_ingest,
        skip_dir_names=set(BLOCKED_INGEST_SEGMENTS),
        **payload,
    )
```

- [ ] **Step 5: Add internal `skip_dir_names` support**

In `src/hks/commands/ingest.py`, replace `run()` with:

```python
def run(
    path: Path,
    *,
    prune: bool = False,
    pptx_notes: bool = True,
    skip_dir_names: set[str] | None = None,
) -> QueryResponse:
    summary = run_ingest(path, prune=prune, pptx_notes=pptx_notes, skip_dir_names=skip_dir_names)
    response = _summary_to_response(summary)
    if summary.failures:
        raise KSError(
            "ingest 完成，但有資料錯誤",
            exit_code=ExitCode.DATAERR,
            code="DATAERR",
            details=[f"{issue.path}: {issue.reason}" for issue in summary.failures],
            response=response,
        )
    return response
```

In `src/hks/adapters/core.py`, update `hks_ingest()` signature and `_run_command()` call:

```python
def hks_ingest(
    *,
    path: str,
    prune: bool = False,
    pptx_notes: str = "include",
    ks_root: str | None = None,
    request_id: str | None = None,
    skip_dir_names: set[str] | None = None,
) -> dict[str, Any]:
```

Pass it to `ingest_command.run`:

```python
        skip_dir_names=skip_dir_names,
```

> **Note on `validate_tool_input`**: `hks_ingest` calls `validate_tool_input("hks_ingest", ...)` before `_run_command`. After HTTP path resolution, `payload["path"]` is an absolute resolved path (e.g. `/Users/me/sources/atlas.md`). Verify that the `hks_ingest` JSON schema allows absolute paths — if the schema enforces relative paths, add `skip_dir_names` to the excluded fields or pass `path` outside `payload` validation.

- [ ] **Step 6: Add directory-prune traversal to ingest pipeline**

In `src/hks/ingest/pipeline.py`, add `import os`.

Replace `discover_files()`:

```python
def discover_files(path: Path, *, skip_dir_names: set[str] | None = None) -> list[Path]:
    if not path.exists():
        raise KSError(
            f"path not found: {path}",
            exit_code=ExitCode.NOINPUT,
            code="NOINPUT",
            hint="請提供存在的檔案或目錄",
        )
    if path.is_file():
        return [path]
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(path):
        if skip_dir_names:
            dirnames[:] = sorted(name for name in dirnames if name not in skip_dir_names)
        else:
            dirnames[:] = sorted(dirnames)
        for filename in sorted(filenames):
            files.append(Path(root) / filename)
    return files
```

Replace the start of `ingest()`:

```python
def ingest(
    path: Path,
    *,
    prune: bool = False,
    pptx_notes: bool = True,
    skip_dir_names: set[str] | None = None,
) -> IngestSummary:
    source_root = path.resolve(strict=False)
    files = discover_files(source_root, skip_dir_names=skip_dir_names)
```

- [ ] **Step 7: Run HTTP ingest allowlist tests**

Run: `uv run pytest tests/integration/test_http_ingest_allowlist.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/hks/adapters/http_security.py src/hks/adapters/http_server.py src/hks/adapters/core.py src/hks/commands/ingest.py src/hks/ingest/pipeline.py tests/integration/test_http_ingest_allowlist.py
git commit -m "feat(http): restrict ingest to configured source roots"
```

---

## Task 6: Update Existing HTTP Tests

**Files:**
- Modify: `tests/integration/test_http_adapter.py`
- Modify: `tests/integration/test_catalog_http.py`
- Search and modify any `TestClient(create_app())` tests that call mutating endpoints.

- [ ] **Step 1: Add shared headers/root setup in `test_http_adapter.py`**

In `tests/integration/test_http_adapter.py`, add:

```python
def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers
```

Update `test_http_adapter_query_ingest_lint_endpoints()`:

```python
@pytest.mark.integration
def test_http_adapter_query_ingest_lint_endpoints(monkeypatch, working_docs, tmp_path) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    monkeypatch.setenv("HKS_API_INGEST_ROOTS", f"docs={working_docs.parent}")
    client = TestClient(create_app())

    ingest = client.post(
        "/ingest",
        headers=_headers("secret"),
        json={
            "ks_root": str(tmp_path / "ks"),
            "source_root_id": "docs",
            "path": working_docs.name,
        },
    )
    assert ingest.status_code == 200
```

For read-only calls (`/query`, `/lint`) in the same test, pass `headers=_headers()` (Host only) and `ks_root` in JSON.

- [ ] **Step 2: Update catalog HTTP workspace register test**

In `tests/integration/test_catalog_http.py`, add:

```python
def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"host": "127.0.0.1"}
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers
```

Change the test signature to include `monkeypatch`:

```python
def test_http_catalog_sources_and_workspace_query(monkeypatch, tmp_path, working_docs) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
```

Pass headers:

```python
    sources = client.post("/catalog/sources", headers=_headers(), json={"ks_root": str(ks_root)}).json()

    registered = client.post(
        "/workspaces",
        headers=_headers("secret"),
        json={
            "action": "register",
            "workspace_id": "proj-a",
            "ks_root": str(ks_root),
            "registry_path": str(registry),
        },
    ).json()
```

Also update `test_http_catalog_error_uses_adapter_envelope` — the invalid workspace register call also needs a Host header and bearer token, otherwise the middleware will reject it with `HTTP_HOST_FORBIDDEN` before the validation error can fire:

```python
def test_http_catalog_error_uses_adapter_envelope(monkeypatch) -> None:
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    response = TestClient(create_app()).post(
        "/workspaces",
        headers={"host": "127.0.0.1", "authorization": "Bearer secret"},
        json={"action": "register", "workspace_id": "../bad", "ks_root": "/tmp/ks"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["exit_code"] == 2
```

- [ ] **Step 3: Search for remaining TestClient HTTP calls**

Run: `rg -n 'TestClient\\(create_app\\(\\)\\)|client\\.post\\(\"/(ingest|workspaces|coord|llm|wiki|graphify|watch/run)' tests`

Expected: every mutating HTTP call includes Host and, when required, `Authorization: Bearer`.

- [ ] **Step 4: Run HTTP adapter tests**

Run:

```bash
uv run pytest tests/integration/test_http_adapter.py tests/integration/test_catalog_http.py tests/integration/test_http_security.py tests/integration/test_http_ingest_allowlist.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_http_adapter.py tests/integration/test_catalog_http.py
git commit -m "test(http): update adapter tests for security guards"
```

---

## Task 7: MCP and Adapter Contract Regression

**Files:**
- Modify: `tests/integration/test_mcp_query.py`
- Modify: `tests/integration/test_mcp_ingest_lint.py`
- Modify: `tests/contract/test_mcp_contract.py`

- [ ] **Step 1: Add MCP no-token regression**

Append to `tests/integration/test_mcp_query.py`:

```python
@pytest.mark.integration
def test_mcp_does_not_require_http_token(monkeypatch, working_docs) -> None:
    monkeypatch.delenv("HKS_API_TOKEN", raising=False)
    core.hks_ingest(path=str(working_docs))

    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary"},
    )

    assert payload["source"] == ["wiki"]
    assert "ok" not in payload
```

- [ ] **Step 2: Add MCP explicit root regression**

Append:

```python
@pytest.mark.integration
def test_mcp_explicit_ks_root_uses_context(monkeypatch, working_docs, tmp_path) -> None:
    ks_root = tmp_path / "mcp-ks"
    core.hks_ingest(path=str(working_docs), ks_root=str(ks_root))
    monkeypatch.setenv("KS_ROOT", str(tmp_path / "wrong-ks"))

    payload = anyio.run(
        _call_tool,
        "hks_query",
        {"question": "Project Atlas summary", "ks_root": str(ks_root)},
    )

    assert payload["source"] == ["wiki"]
    assert "Atlas" in payload["answer"]
```

- [ ] **Step 3: Run MCP regression tests**

Run: `uv run pytest tests/integration/test_mcp_query.py tests/integration/test_mcp_ingest_lint.py tests/contract/test_mcp_contract.py -q`

Expected: PASS. MCP must not require HTTP bearer token or HTTP ingest roots.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_mcp_query.py tests/integration/test_mcp_ingest_lint.py tests/contract/test_mcp_contract.py
git commit -m "test(mcp): preserve local adapter semantics after http hardening"
```

---

## Task 8: Documentation and Contract Notes

**Files:**
- Modify: `docs/configuration.md`
- Modify: `mcp/http.md`
- Modify: `specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml`

- [ ] **Step 1: Document new config**

In `docs/configuration.md`, add this section near existing env/config settings:

```markdown
### HTTP API security

`hks-api` is an optional loopback facade. Mutating endpoints are disabled unless `HKS_API_TOKEN` is set.

| Env | Meaning |
|---|---|
| `HKS_API_TOKEN` | Bearer token required for HTTP mutating endpoints |
| `HKS_API_HOST_ALLOWLIST` | Allowed Host header names; default `127.0.0.1,localhost,::1` |
| `HKS_API_REJECT_BROWSER_REQUESTS` | Reject mutating requests with `Origin` or `Sec-Fetch-Site`; default true |
| `HKS_API_INGEST_ROOTS` | Comma-separated named source roots, e.g. `docs=/Users/me/docs,shared=/Volumes/shared` |

HTTP `/ingest` only accepts relative paths under `HKS_API_INGEST_ROOTS`. CLI `ks ingest` and MCP `hks_ingest` keep their local-tool path semantics.
```

- [ ] **Step 2: Document HTTP usage**

In `mcp/http.md`, add:

```markdown
## HTTP security

Mutating calls require:

```bash
export HKS_API_TOKEN="dev-secret"
export HKS_API_INGEST_ROOTS="docs=$PWD/testhks"
uv run hks-api
```

Example ingest:

```bash
curl -sS \
  -H "Host: 127.0.0.1" \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ks_root":"/absolute/path/to/.hks-runs/demo/ks","source_root_id":"docs","path":"project-atlas.txt"}' \
  http://127.0.0.1:8766/ingest
```

Browser-origin mutating requests are rejected by default. Use CLI or MCP for trusted local automation when you need arbitrary local file paths.
```

- [ ] **Step 3: Update OpenAPI security annotations**

In `specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml`, add a bearer scheme under `components.securitySchemes`:

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
```

Add `security` to mutating operations:

```yaml
security:
  - BearerAuth: []
```

Update `HksIngestInput` schema to include `source_root_id`:

```yaml
source_root_id:
  type: string
  description: Named source root from HKS_API_INGEST_ROOTS.
```

- [ ] **Step 4: Run docs/contract checks**

Run: `uv run pytest tests/contract/test_http_api_contract.py -q`

Expected: PASS. If the test asserts exact paths only, update it to include security scheme assertions without relaxing path coverage.

- [ ] **Step 5: Commit**

```bash
git add docs/configuration.md mcp/http.md specs/006-mcp-api-adapter/contracts/http-api.openapi.yaml tests/contract/test_http_api_contract.py
git commit -m "docs(http): document api security boundaries"
```

---

## Task 9: Final Verification

**Files:**
- No source edits unless verification finds a regression.

- [ ] **Step 1: Run targeted test bundle**

Run:

```bash
uv run pytest \
  tests/unit/core/test_runtime_context.py \
  tests/unit/adapters/test_core.py \
  tests/integration/test_adapter_runtime_context.py \
  tests/integration/test_http_security.py \
  tests/integration/test_http_ingest_allowlist.py \
  tests/integration/test_http_adapter.py \
  tests/integration/test_catalog_http.py \
  tests/integration/test_mcp_query.py \
  tests/contract/test_http_api_contract.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full project gates**

Run:

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

Expected: all pass.

- [ ] **Step 3: Manual smoke for HTTP security**

Run:

```bash
export HKS_API_TOKEN=dev-secret
export HKS_API_INGEST_ROOTS="docs=$PWD/tests/fixtures/valid"
uv run hks-api --port 8766
```

In another shell:

```bash
curl -sS -H "Host: 127.0.0.1" http://127.0.0.1:8766/lint -d '{}' -H 'Content-Type: application/json'
curl -sS -H "Host: evil.example" http://127.0.0.1:8766/lint -d '{}' -H 'Content-Type: application/json'
curl -sS -H "Host: 127.0.0.1" http://127.0.0.1:8766/ingest -d '{"path":"project-atlas.txt"}' -H 'Content-Type: application/json'
curl -sS -H "Host: 127.0.0.1" -H "Authorization: Bearer dev-secret" http://127.0.0.1:8766/ingest -d '{"ks_root":"'$PWD'/.hks-runs/014-smoke/ks","source_root_id":"docs","path":"project-atlas.txt"}' -H 'Content-Type: application/json'
```

Expected:

- first curl returns schema-valid lint response or adapter envelope
- second curl returns `HTTP_HOST_FORBIDDEN`
- third curl returns `HTTP_AUTH_REQUIRED`
- fourth curl succeeds and creates `.hks-runs/014-smoke/ks/manifest.json`

- [ ] **Step 4: Confirm the working tree state**

Run: `git status --short`

Expected: either clean, or only intentional verification fixes remain. If fixes remain, return to the task that owns the changed file, apply the task's targeted test command, and use that task's commit pattern.

---

## Self-Review Checklist

- 014 runtime context: Task 1, Task 2, Task 3.
- `adapters/core.py` and `workspace/service.py` no longer own env-mutating scoped root: Task 2, Task 3.
- MCP adapter stays local and does not inherit HTTP auth/path restrictions: Task 7.
- HTTP Host/auth/browser guard is middleware-level, not per endpoint: Task 4.
- HTTP `/ingest` requires configured named source roots and relative path: Task 5.
- HTTP hidden-dir skip behavior is covered for directory ingest: Task 5.
- Existing HTTP tests updated for the new boundary: Task 6.
- Docs and OpenAPI contract updated: Task 8.
- Full verification gates match repo guidance: Task 9.
