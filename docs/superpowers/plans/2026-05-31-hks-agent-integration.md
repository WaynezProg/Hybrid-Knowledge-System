# HKS Agent Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `hks-mcp` / `hks-api` 提供 **agent profile**，讓 Cursor / Codex / Claude / OpenClaw 以 `workspace_id` 做 query，並在 task-end 僅 ingest `$HKS_SESSION2MEMORY_EXPORT_ROOT/<workspace_id>/` 下之 session2memory Markdown。

**Architecture:** 新增 adapter 層驗證（路徑 allowlist + frontmatter discipline + slugify）與 `hks_workspace_ingest_session_memory` core 函式（auto-register → 委派既有 `ingest_command`）。MCP/HTTP 以 profile allowlist 隱藏 full tools；agent 路徑禁止裸 `ks_root`。

**Tech Stack:** Python 3.12、FastMCP、Starlette、`typer`、`pytest`、`jsonschema` contract tests

**Design spec:** [../specs/2026-05-31-hks-agent-integration-design.md](../specs/2026-05-31-hks-agent-integration-design.md)

---

## File map

| File | Responsibility |
|------|----------------|
| `src/hks/adapters/agent_config.py` | **Create.** `HKS_AGENT_PROFILE`、export/ks_root base 解析、`is_agent_profile()` |
| `src/hks/adapters/workspace_id.py` | **Create.** `slugify_workspace_id()`、`resolve_workspace_id_from_project_root()` |
| `src/hks/adapters/session_memory_source.py` | **Create.** 路徑解析、frontmatter 驗證、目錄掃描 fail-fast |
| `src/hks/adapters/core.py` | **Modify.** `hks_workspace_ingest_session_memory`、`hks_session_memory_summary`、agent 專用錯誤 |
| `src/hks/adapters/mcp_server.py` | **Modify.** `--profile agent`、條件註冊 tools |
| `src/hks/adapters/http_server.py` | **Modify.** 新路由、agent profile 403 guard |
| `src/hks/core/config.py` | **Modify.** `HKS_SESSION2MEMORY_EXPORT_ROOT`、`HKS_KS_ROOT_BASE` |
| `tests/unit/adapters/test_workspace_id.py` | **Create.** slugify + collision suffix |
| `tests/unit/adapters/test_session_memory_source.py` | **Create.** allow/deny paths + frontmatter |
| `tests/contract/test_agent_profile_contract.py` | **Create.** tool manifest + forbidden HTTP |
| `tests/integration/test_agent_profile_ingest.py` | **Create.** end-to-end ingest + reject harness md |
| `mcp/tools/hks-mcp-tools.json` | **Modify.** 新增 agent tools 條目 |
| `mcp/README.md` | **Modify.** agent profile 啟動與 env |
| `docs/configuration.md` | **Modify.** 新環境變數說明 |
| `skill/hks-knowledge-system/` | **Modify.** agent task-end ingest 片段 |

---

### Task 1: 環境變數與 workspace_id slugify

**Files:**
- Create: `src/hks/adapters/workspace_id.py`
- Modify: `src/hks/core/config.py`
- Create: `tests/unit/adapters/test_workspace_id.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/unit/adapters/test_workspace_id.py
from __future__ import annotations

from pathlib import Path

import pytest

from hks.adapters.workspace_id import slugify_workspace_id


@pytest.mark.parametrize(
    ("basename", "expected"),
    [
        ("hks", "hks"),
        ("My Project", "my-project"),
        ("foo__bar", "foo-bar"),
        ("!!!", "project"),
    ],
)
def test_slugify_workspace_id(basename: str, expected: str) -> None:
    assert slugify_workspace_id(basename) == expected


def test_slugify_workspace_id_collision_suffix() -> None:
    root = Path("/tmp/aaa/hks")
    slug = slugify_workspace_id("hks", project_root=root, reserved={})
    assert slug == "hks"
    other = Path("/tmp/bbb/hks")
    slug2 = slugify_workspace_id(
        "hks",
        project_root=other,
        reserved={"hks": root},
    )
    assert slug2.startswith("hks-")
    assert len(slug2) == len("hks-") + 8
```

- [ ] **Step 2: 跑測試確認 FAIL**

```bash
cd /Users/waynetu/claw_prog/projects/04-kurisu-github/hks
uv run pytest tests/unit/adapters/test_workspace_id.py -v
```

Expected: `ModuleNotFoundError: hks.adapters.workspace_id`

- [ ] **Step 3: 實作 `workspace_id.py`**

```python
# src/hks/adapters/workspace_id.py
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_MULTI_HYPHEN = re.compile(r"-+")


def slugify_workspace_id(
    basename: str,
    *,
    project_root: Path | None = None,
    reserved: dict[str, Path] | None = None,
) -> str:
    slug = basename.strip().lower().replace(" ", "-").replace("_", "-")
    slug = _MULTI_HYPHEN.sub("-", _SLUG_RE.sub("", slug)).strip("-")
    if not slug:
        slug = "project"
    if project_root is None or not reserved:
        return slug
    existing = reserved.get(slug)
    if existing is None or existing.resolve() == project_root.resolve():
        return slug
    digest = hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:8]
    return f"{slug}-{digest}"
```

在 `src/hks/core/config.py` 新增常數：

```python
ENV_SESSION2MEMORY_EXPORT_ROOT = "HKS_SESSION2MEMORY_EXPORT_ROOT"
ENV_KS_ROOT_BASE = "HKS_KS_ROOT_BASE"
ENV_AGENT_PROFILE = "HKS_AGENT_PROFILE"
```

- [ ] **Step 4: 跑測試確認 PASS**

```bash
uv run pytest tests/unit/adapters/test_workspace_id.py -v
```

- [ ] **Step 5: Commit**

```bash
git add -f src/hks/adapters/workspace_id.py src/hks/core/config.py tests/unit/adapters/test_workspace_id.py
git commit -m "feat(adapters): 新增 workspace_id slugify 與 agent 環境變數鍵"
```

---

### Task 2: session2memory 來源驗證模組

**Files:**
- Create: `src/hks/adapters/session_memory_source.py`
- Create: `tests/unit/adapters/test_session_memory_source.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/unit/adapters/test_session_memory_source.py
from __future__ import annotations

from pathlib import Path

import pytest

from hks.adapters.session_memory_source import (
    SessionMemorySourceError,
    assert_session_memory_tree,
    resolve_export_path,
)


def test_resolve_export_path_under_workspace(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    workspace_id = "hks"
    daily = export_root / workspace_id / "daily" / "2026-05-31.md"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "---\nsource_domain: session_memory\ngenerator: session2memory\n---\n# day\n",
        encoding="utf-8",
    )
    resolved = resolve_export_path(
        export_root=export_root,
        workspace_id=workspace_id,
        path="daily/2026-05-31.md",
    )
    assert resolved == daily.resolve()


def test_reject_path_outside_workspace(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    other = export_root / "other" / "x.md"
    other.parent.mkdir(parents=True)
    other.write_text("x", encoding="utf-8")
    with pytest.raises(SessionMemorySourceError) as exc:
        resolve_export_path(
            export_root=export_root,
            workspace_id="hks",
            path=str(other),
        )
    assert exc.value.code == "WORKSPACE_PATH_OUT_OF_ROOT"


def test_reject_non_session2memory_md(tmp_path: Path) -> None:
    export_root = tmp_path / "export"
    bad = export_root / "hks" / "raw.md"
    bad.parent.mkdir(parents=True)
    bad.write_text("# no frontmatter\n", encoding="utf-8")
    with pytest.raises(SessionMemorySourceError) as exc:
        assert_session_memory_tree(
            root=bad.parent,
            workspace_id="hks",
        )
    assert exc.value.code == "INGEST_SOURCE_DISALLOWED"
```

- [ ] **Step 2: 跑測試確認 FAIL**

```bash
uv run pytest tests/unit/adapters/test_session_memory_source.py -v
```

- [ ] **Step 3: 實作 `session_memory_source.py`**

實作要點（須完整寫入檔案，不可留空）：

- `SessionMemorySourceError(code, message, exit_code=ExitCode.DATAERR)`
- `resolve_export_path(export_root, workspace_id, path)` → `Path`；`Path(path).resolve()` 必須 `is_relative_to((export_root/workspace_id).resolve())`
- `_parse_frontmatter(text) -> dict`：簡易 `---` 區塊解析（或重用 `hks.ingest.parsers.md` 若已有可匯入函式，避免重複則抽共用）
- `_is_session_memory_metadata(meta) -> bool`：邏輯對齊 `src/hks/routing/session_memory.py` 的 `_is_session_memory_metadata`
- `assert_session_memory_tree(root, workspace_id)`：若 `root` 是檔案則驗單檔；若是目錄則 `rglob("*.md")` 全驗；frontmatter `workspace_id` 存在且不等於請求 id → `WORKSPACE_ID_MISMATCH`

- [ ] **Step 4: 跑測試確認 PASS**

```bash
uv run pytest tests/unit/adapters/test_session_memory_source.py -v
```

- [ ] **Step 5: Commit**

```bash
git add -f src/hks/adapters/session_memory_source.py tests/unit/adapters/test_session_memory_source.py
git commit -m "feat(adapters): session2memory ingest 路徑與 frontmatter 驗證"
```

---

### Task 3: `hks_workspace_ingest_session_memory` core

**Files:**
- Create: `src/hks/adapters/agent_config.py`
- Modify: `src/hks/adapters/core.py`
- Create: `tests/integration/test_agent_profile_ingest.py`（先寫 ingest 成功/失敗案例）

- [ ] **Step 1: 寫失敗 integration 測試**

```python
# tests/integration/test_agent_profile_ingest.py (excerpt — 完整檔於實作時補齊 fixtures)
@pytest.mark.integration
def test_workspace_ingest_session_memory_auto_registers_and_ingests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_root = tmp_path / "export"
    ks_base = tmp_path / "ks-base"
    registry = tmp_path / "workspaces.json"
    workspace_id = "demo"
    daily = export_root / workspace_id / "daily" / "2026-05-31.md"
    daily.parent.mkdir(parents=True)
    daily.write_text(
        "---\nhks_type: session_daily\n"
        "date: 2026-05-31\n"
        "source_domain: session_memory\n"
        "generator: session2memory\n"
        "workspace_id: demo\n"
        "---\n# 2026-05-31\n\n- item\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HKS_SESSION2MEMORY_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("HKS_KS_ROOT_BASE", str(ks_base))
    monkeypatch.setenv("HKS_WORKSPACE_REGISTRY", str(registry))
    monkeypatch.setenv("HKS_EMBEDDING_MODEL", "simple")

    from hks.adapters.core import hks_workspace_ingest_session_memory

    payload = hks_workspace_ingest_session_memory(
        workspace_id=workspace_id,
        path="daily/2026-05-31.md",
    )
    assert payload["trace"]["steps"]
    assert (ks_base / workspace_id / "manifest.json").exists()
```

- [ ] **Step 2: 跑測試確認 FAIL**

```bash
uv run pytest tests/integration/test_agent_profile_ingest.py::test_workspace_ingest_session_memory_auto_registers_and_ingests -v
```

- [ ] **Step 3: 實作 `agent_config.py` + core 函式**

`agent_config.py`：

```python
def is_agent_profile() -> bool:
    return os.environ.get(ENV_AGENT_PROFILE, "").strip() in {"1", "true", "yes"}

def require_export_root() -> Path: ...
def ks_root_for_workspace(workspace_id: str) -> Path: ...
```

`core.hks_workspace_ingest_session_memory` 流程：

1. 驗證 `workspace_id` 符合 `^[a-z0-9][a-z0-9-]*$`（不符 → `WORKSPACE_ID_INVALID`）
2. `resolve_export_path` + `assert_session_memory_tree`
3. 若 registry 無 id：`hks_workspace_register(workspace_id=..., ks_root=str(ks_root_for_workspace(...)), label=workspace_id)`（內部呼叫，不經 MCP）
4. `hks_ingest(path=str(resolved), ks_root=str(ks_root), skip_dir_names=...)` — ingest 目錄時傳 `resolved` 的 parent 或檔案本身，與既有 tree ingest 行為一致
5. 回傳 ingest command 的 dict payload

- [ ] **Step 4: 跑 integration 測試 PASS + 拒絕案例**

新增 `test_rejects_harness_like_markdown`：無 frontmatter 的 `.md` → `INGEST_SOURCE_DISALLOWED`。

```bash
uv run pytest tests/integration/test_agent_profile_ingest.py -v
```

- [ ] **Step 5: Commit**

```bash
git add -f src/hks/adapters/agent_config.py src/hks/adapters/core.py tests/integration/test_agent_profile_ingest.py
git commit -m "feat(adapters): workspace session-memory ingest 與 auto-register"
```

---

### Task 4: Agent profile allowlist（MCP）

**Files:**
- Modify: `src/hks/adapters/mcp_server.py`
- Modify: `mcp/tools/hks-mcp-tools.json`
- Create: `tests/contract/test_agent_profile_contract.py`

- [ ] **Step 1: 寫 contract 測試 — agent profile tool 名稱集合**

```python
# tests/contract/test_agent_profile_contract.py
AGENT_TOOLS = frozenset({
    "hks_workspace_query",
    "hks_workspace_ingest_session_memory",
    "hks_workspace_show",
    "hks_workspace_list",
    "hks_session_memory_summary",
    "hks_source_list",
    "hks_source_show",
})

def test_agent_profile_exposes_only_allowlisted_tools(monkeypatch):
    monkeypatch.setenv("HKS_AGENT_PROFILE", "1")
    from hks.adapters.mcp_server import list_tool_names_for_current_profile
    assert set(list_tool_names_for_current_profile()) == AGENT_TOOLS
```

（實作時抽出 `list_tool_names_for_current_profile()` 供測試；或透過 FastMCP 內部 registry introspection。）

- [ ] **Step 2: 修改 `mcp_server.py`**

- `main()` 增加 `--profile {full,agent}`，設定 `HKS_AGENT_PROFILE`
- `create_server(profile: str = "full")`：agent 時不註冊 `hks_query`、`hks_ingest`、`hks_graphify_*` 等
- 新增 tools：

```python
@server.tool()
def hks_workspace_ingest_session_memory(
    workspace_id: str,
    path: str,
    project_root: str | None = None,
) -> Any:
    ...
```

- `hks_session_memory_summary` 委派 `session_memory_command.run_summary`（經 `_run_command` 或等價包裝），必填 `workspace`

- [ ] **Step 3: 更新 `mcp/tools/hks-mcp-tools.json`**

新增 `hks_workspace_ingest_session_memory` 與 `agent_profile` 說明區塊。

- [ ] **Step 4: 跑 contract + `uv run hks-mcp --help`**

```bash
uv run pytest tests/contract/test_agent_profile_contract.py -v
HKS_AGENT_PROFILE=1 uv run hks-mcp --help
```

- [ ] **Step 5: Commit**

```bash
git add -f src/hks/adapters/mcp_server.py mcp/tools/hks-mcp-tools.json tests/contract/test_agent_profile_contract.py
git commit -m "feat(mcp): agent profile allowlist 與 session-memory ingest tool"
```

---

### Task 5: Agent profile HTTP 路由與 403 guard

**Files:**
- Modify: `src/hks/adapters/http_server.py`
- Modify: `tests/integration/test_http_adapter.py`

- [ ] **Step 1: 寫失敗測試 — forbidden route**

```python
def test_agent_profile_forbids_generic_ingest(monkeypatch):
    monkeypatch.setenv("HKS_AGENT_PROFILE", "1")
    monkeypatch.setenv("HKS_API_TOKEN", "secret")
    client = TestClient(create_app())
    response = client.post(
        "/ingest",
        json={"path": "x"},
        headers=_headers("secret"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_PROFILE_FORBIDDEN"
```

- [ ] **Step 2: 實作路由**

- `POST /workspaces/{workspace_id}/ingest/session-memory` → `core.hks_workspace_ingest_session_memory`
- `POST /session-memory/summary` → `core.hks_session_memory_summary`（包裝 `run_summary`）
- `create_app()` 開頭 middleware：若 `is_agent_profile()` 且 path 在 forbidden 清單（`/ingest`、`/query`、`/watch/*`…）→ 403 JSON

- [ ] **Step 3: workspace-scoped catalog**

`hks_source_list/show` 在 agent HTTP 路徑需從 body 取 `workspace_id` 並解析 `ks_root`（可新增 `/workspaces/{id}/catalog/sources` 或擴充既有 payload — 與 spec §4.5 對齊）。

- [ ] **Step 4: 跑測試**

```bash
uv run pytest tests/integration/test_http_adapter.py tests/integration/test_agent_profile_ingest.py -v
```

- [ ] **Step 5: Commit**

```bash
git add -f src/hks/adapters/http_server.py tests/integration/test_http_adapter.py
git commit -m "feat(http): agent profile 路由與 forbidden endpoint 403"
```

---

### Task 6: `hks_session_memory_summary` adapter 與 workspace query 強制

**Files:**
- Modify: `src/hks/adapters/core.py`
- Modify: `tests/integration/test_session_memory_query.py`（adapter 層 smoke，可選）

- [ ] **Step 1: 實作 `core.hks_session_memory_summary`**

```python
def hks_session_memory_summary(
    *,
    workspace_id: str,
    date_from: str,
    date_to: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    ks_root = _resolve_workspace_ks_root(workspace_id, request_id=request_id)
    return _run_command(
        session_memory_command.run_summary,
        date_from=date_from,
        date_to=date_to,
        workspace=workspace_id,
        ks_root=str(ks_root),
        request_id=request_id,
    )
```

- [ ] **Step 2: agent profile 下 `hks_workspace_query` 拒絕缺失 workspace_id**（MCP schema 已 required；HTTP body 驗證）

- [ ] **Step 3: pytest 既有 session-memory 測試全綠**

```bash
uv run pytest tests/integration/test_session_memory_query.py tests/unit/routing/test_session_memory_intent.py -v
```

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(adapters): session-memory summary 與 workspace 解析輔助"
```

---

### Task 7: 文件、skill、configuration

**Files:**
- Modify: `mcp/README.md`
- Modify: `docs/configuration.md`
- Modify: `docs/main.md`（短節 + 連結 spec）
- Modify: `skill/hks-knowledge-system/SKILL.md`、`workflows/ingest-query.md`

- [ ] **Step 1: `docs/configuration.md` 新增三變數與範例**

- [ ] **Step 2: `mcp/README.md` 新增 agent profile 啟動**

```bash
export HKS_SESSION2MEMORY_EXPORT_ROOT="$HOME/session2memory/export"
export HKS_KS_ROOT_BASE="$HOME/.local/share/hks/workspaces"
export HKS_API_TOKEN='...'
uv run hks-mcp --profile agent --transport stdio
uv run hks-api --profile agent --host 127.0.0.1 --port 8766
```

- [ ] **Step 3: skill 增補 task-end 範例**（`hks_workspace_ingest_session_memory` + `writeback=no` query）

- [ ] **Step 4: Commit**

```bash
git add -f mcp/README.md docs/configuration.md docs/main.md skill/hks-knowledge-system/
git commit -m "docs: agent profile 操作說明與環境變數"
```

---

### Task 8: 全量驗證

- [ ] **Step 1: Lint / typecheck**

```bash
uv run ruff check src/hks/adapters tests/unit/adapters tests/contract/test_agent_profile_contract.py tests/integration/test_agent_profile_ingest.py
uv run mypy src/hks/adapters
```

- [ ] **Step 2: 相關 pytest 子集**

```bash
uv run pytest tests/unit/adapters tests/contract/test_agent_profile_contract.py tests/integration/test_agent_profile_ingest.py tests/integration/test_http_adapter.py -v
```

- [ ] **Step 3: 可選全量 `uv run pytest`**（CI 前）

- [ ] **Step 4: Commit（若有遺漏修正）**

---

## Spec coverage checklist

| Spec § | Task |
|--------|------|
| §1 邊界、不碰 harness | Task 2–3 拒絕非 session2memory；文件 Task 7 |
| §2 workspace / auto-register | Task 1, 3 |
| §3 source discipline | Task 2 |
| §4 agent MCP/HTTP surface | Task 4, 5, 6 |
| §5 error codes | Task 2 `SessionMemorySourceError`、Task 5 403 |
| §6 測試 | Task 1–6, 8 |
| §7 rollout docs | Task 7 |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-31-hks-agent-integration.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每個 Task 一個 subagent，任務間 review

**2. Inline Execution** — 本 session 用 executing-plans 批次執行

Which approach?
