# Research: Phase 3 階段三 — MCP / API adapter

## Decision: 使用官方 `mcp` Python SDK + FastMCP

- **Decision**: 006 MVP 以官方 `mcp` Python SDK 實作 MCP server，使用 `FastMCP` 暴露 tools。
- **Rationale**: 官方 MCP SDK 列出 Python SDK 為 Tier 1，且 Python SDK 文件明確支援建立 servers/clients、stdio、SSE、Streamable HTTP。官方安裝文件指定 PyPI package name 為 `mcp`，可用 `uv add mcp`。
- **Alternatives considered**:
  - 手刻 JSON-RPC / MCP protocol：拒絕。protocol drift 風險高，且測試成本不必要。
  - 第三方 FastMCP package：拒絕。006 應優先使用官方 SDK，除非 implementation 期間遇到官方 SDK blocker。

Refs:
- https://modelcontextprotocol.io/docs/sdk
- https://py.sdk.modelcontextprotocol.io/
- https://py.sdk.modelcontextprotocol.io/installation/

## Decision: MVP transport 為 stdio + Streamable HTTP

- **Decision**: MCP server MUST 支援 stdio 與 Streamable HTTP；Streamable HTTP MUST 預設綁定 loopback。SSE 不作 MVP requirement。
- **Rationale**: stdio 是本機 agent integration 的低風險入口；Streamable HTTP 是官方 Python SDK 支援的標準 transport，可支撐本機 inspector / HTTP client 測試。
- **Alternatives considered**:
  - 只做 HTTP REST：拒絕。這會偏離 agent-first 與 MCP MVP。
  - 同時支援 stdio / SSE / Streamable HTTP / REST：拒絕。一次支援太多 surface，implementation 風險高。

## Decision: Adapter 重用 command/core 層，不 shell out

- **Decision**: `hks.adapters.core` 直接呼叫 `hks.commands.query.run`、`hks.commands.ingest.run`、`hks.commands.lint.run`，捕捉 `KSError` 並轉為 adapter error envelope。
- **Rationale**: 直接呼叫可保留型別與 schema validation，避免 subprocess stdout/stderr parsing。Command 層已是 CLI contract 的最小穩定 boundary。
- **Alternatives considered**:
  - 透過 `subprocess` 呼叫 `uv run ks ...`：拒絕。慢、難測、會複製 CLI parsing 問題。
  - 直接呼叫更底層 pipeline：拒絕。會繞過現有 command response builder 與 error contract。

## Decision: 成功 response 直接回 HKS QueryResponse payload

- **Decision**: MCP tool successful structured content MUST 直接是現有 `QueryResponse.to_dict()` shape。
- **Rationale**: Agent 已依賴 HKS schema；adapter 不應創造第二套 success schema。
- **Alternatives considered**:
  - 包一層 `{ok, data, error}`：拒絕作為 success shape，會讓 agent 處理兩種 contract。錯誤才用 adapter error envelope。

## Decision: 錯誤回傳 adapter error envelope

- **Decision**: adapter error envelope 固化為 `{ok:false, error:{code, exit_code, message, hint?, details?}, response?}`；MCP 層可用 `isError=true`，但 structured content 仍保留 envelope。
- **Rationale**: MCP `ToolError` 只有文字時會丟失 HKS exit code；envelope 可讓 agent 精準分支。
- **Alternatives considered**:
  - 只丟 MCP ToolError 字串：拒絕。無法穩定解析。

## Decision: Query adapter 預設 `writeback=no`

- **Decision**: `hks_query.writeback` 預設值與 CLI 不同，adapter default 固定為 `no`；caller 可明確傳 `auto|yes|ask`。
- **Rationale**: Agent 背景查詢不應默默寫回 wiki。這是 adapter safety default，不改 CLI 行為。
- **Alternatives considered**:
  - 沿用 CLI default `auto`：拒絕。會把 agent read path 變成 hidden mutation path。

## Decision: HTTP REST 是 P2 optional

- **Decision**: `http-api.openapi.yaml` 先定義 optional `/query`、`/ingest`、`/lint`；tasks 排在 MCP MVP 之後。
- **Rationale**: 使用者要求 API / MCP adapter，但 agent-first 價值在 MCP。REST 對泛用 tooling 有價值，但不該拖住 MVP。
- **Alternatives considered**:
  - 006 同時完整交付 MCP + REST：拒絕。測試矩陣擴大，且會模糊最小完成定義。

## Decision: 不做 auth / RBAC，靠 local-only boundary

- **Decision**: 006 不實作 authentication / RBAC；MCP stdio 與 loopback binding 是安全邊界。非 loopback host MUST 預設拒絕，除非明確 opt-in。
- **Rationale**: 專案明確非多使用者、非雲端部署；引入 auth 會違反 scope。
- **Alternatives considered**:
  - Bearer token / API key：延後。若未來要 remote API 或 multi-user，再另開 spec。
