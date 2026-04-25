# Data Model: Phase 3 階段三 — MCP / API adapter

## AdapterRequest

外部 adapter call 的標準化輸入。

Fields:
- `tool`: enum，`hks_query | hks_ingest | hks_lint`
- `arguments`: object，依 tool input schema 驗證
- `ks_root`: string | null，optional runtime root override；缺省使用 process `KS_ROOT`
- `request_id`: string | null，optional client correlation id

Validation:
- `tool` MUST 是已註冊 tool。
- `arguments` MUST 通過 `contracts/mcp-tools.schema.json` 對應 input schema。
- `ks_root` 若提供，MUST resolve 成本機路徑；只作 runtime root override，不得作為任意檔案讀取 API。

## Successful Tool Payload

adapter 的成功回應內容。

Fields:
- `answer`: string
- `source`: list[`wiki` | `graph` | `vector`]
- `confidence`: number
- `trace`: object

Rules:
- 成功 payload MUST 直接是 `QueryResponse.to_dict()`，不得包成 `{ok, payload}` 或其他 adapter-specific success envelope。
- `trace.route` value set 不因 adapter 擴充。

## AdapterError

adapter 的錯誤回應。

Fields:
- `ok`: `false`
- `error.code`: string，沿用 `KSError.code` 或 `USAGE`
- `error.exit_code`: integer，`1 | 2 | 65 | 66`
- `error.message`: string
- `error.hint`: string | null
- `error.details`: list[string]
- `response`: `QueryResponse` | null，若 command 層已產生 schema-valid error response 則帶上
- `request_id`: string | null

Rules:
- MCP tool error MUST preserve this envelope in structured content. Preferred implementation is direct `CallToolResult` with `isError=true`; if SDK constraints block structured error content, the tool MUST return a JSON-encoded envelope as text and cover that fallback in tests.
- `response` 若存在，MUST 通過 canonical response schema。

## ToolDefinition

MCP tool metadata。

Fields:
- `name`: `hks_query | hks_ingest | hks_lint`
- `description`: string
- `input_schema`: JSON Schema object
- `output_schema`: JSON Schema object

Rules:
- Tool name MUST use `hks_` prefix，避免與 client 內建 tools 衝突。
- Tool input schema MUST be documented in `contracts/mcp-tools.schema.json`。

## HksQueryInput

Fields:
- `question`: string，minLength 1
- `writeback`: enum `no | auto | yes | ask`，default `no`
- `ks_root`: string | null

Rules:
- `writeback=no` 是 adapter default；這是 adapter safety default，不改 CLI default。

## HksIngestInput

Fields:
- `path`: string，file or directory path
- `prune`: boolean，default `false`
- `pptx_notes`: enum `include | exclude`，default `include`
- `ks_root`: string | null

Rules:
- `path` MUST exist，否則映射 `NOINPUT`。
- `path` 可指向任意本機 file/dir；path safety 禁止的是任意讀取 `/ks/` runtime internals 的 adapter file API，不是禁止 ingest 外部來源。
- 支援格式只可跟目前 runtime 一致：`txt / md / pdf / docx / xlsx / pptx / png / jpg / jpeg`。

## HksLintInput

Fields:
- `strict`: boolean，default `false`
- `severity_threshold`: enum `error | warning | info`，default `error`
- `fix`: enum `none | plan | apply`，default `none`
- `ks_root`: string | null

Rules:
- `fix=apply` MUST preserve 005 allowlist；adapter 不新增修復能力。
