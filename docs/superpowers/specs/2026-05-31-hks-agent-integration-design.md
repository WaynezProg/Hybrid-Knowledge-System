# HKS Agent Integration 設計規格

**狀態**：已核准（brainstorming §1–§4）  
**日期**：2026-05-31  
**相關**：`docs/main.md`、`mcp/README.md`、`specs/012-source-catalog`、`skill/hks-knowledge-system/`

## 摘要

本規格定義 HKS 作為 **查知識** 與 **沉澱專案知識** 的 local backend，透過 **agent profile** 的 MCP/HTTP 介面服務 Cursor、Codex、Claude、OpenClaw。HKS **不參與 harness process**；僅 ingest **session2memory** 產物。每個 git project 對應一個 **workspace**（獨立 `KS_ROOT`），由 coding agent 在任務結束時觸發 ingest。

---

## 1. Scope & Boundaries

### 1.1 系統角色

| 元件 | 職責 | 不負責 |
|------|------|--------|
| **Harness** | 執行 session、產出 raw transcript | 寫入 HKS、知識檢索 |
| **session2memory** | transcript → 結構化 Markdown（`daily/` 等）、frontmatter | 呼叫 HKS、編排 harness |
| **HKS** | ingest 允許來源、更新 wiki/graph/vector/page_tree/manifest；fused query | harness 生命週期、transcript 儲存、session2memory 生成邏輯 |
| **Coding agents**（Cursor / Codex / Claude / **OpenClaw**） | 任務結束觸發 ingest；日常 query | 繞過 source discipline 寫入任意檔案 |

### 1.2 HKS 邊界（硬性）

- **In**：session2memory 產物（見 §3 Source Discipline）。
- **Out**：raw harness transcript、harness orchestration、非 session2memory 的任意 ingest 路徑。
- **能力保留**：full profile 下既有 CLI/MCP/HTTP（graphify、watch、coord 等）不刪除；**agent profile** 僅暴露本規格允許之子集。

### 1.3 非目標

- 019 write-back review queue 實作
- 雲端部署、多使用者 RBAC
- 在 HKS 內實作 session2memory 或 harness
- 以 HKS 取代 agent 本機 transcript 儲存

---

## 2. Workspace & Ingest 流程

### 2.1 目錄慣例

| 概念 | 路徑 / 規則 |
|------|-------------|
| Export root | `$HKS_SESSION2MEMORY_EXPORT_ROOT`（machine-wide，由 operator 設定） |
| Project export | `{export_root}/{workspace_id}/`（session2memory 寫入側維持此結構） |
| KS_ROOT base | `$HKS_KS_ROOT_BASE/{workspace_id}/`（HKS 權威層根目錄） |
| Registry | 既有 `HKS_WORKSPACE_REGISTRY` 或 XDG 預設；記錄 `workspace_id` ↔ `ks_root` |

**一個 project → 一個 workspace → 一個 `KS_ROOT`。** 禁止多個 repo 共用同一 `KS_ROOT`；registry 層級拒絕 duplicate `ks_root` 綁定不同 id（沿用 012 語意）。

### 2.2 `workspace_id` 推導

由 agent 提供 **`project_root`**（git top-level 目錄），server 或 agent 依相同規則計算 `workspace_id`：

1. `basename =` `project_root` 最後一層目錄名。
2. `slug = lowercase(basename)`。
3. 將空白與 `_` 替換為 `-`。
4. 移除不在 `[a-z0-9-]` 的字元。
5. 合併連續 `-`，並去掉首尾 `-`。
6. 若結果為空，使用 `project`。
7. 若 slug 與既有 registry 中另一 `project_root` 衝突（同 id 不同絕對路徑），在 slug 後附加 `-` + `sha256(absolute_project_root)` 前 8 字元（小寫 hex）。

Agent 呼叫 ingest/query 時 **必須** 帶 `workspace_id`；agent profile **禁止** 省略 `workspace_id` 而使用 process 環境內裸 `KS_ROOT`（避免跨 repo 混庫）。

### 2.3 首次 ingest 與 auto-register

1. 解析 `workspace_id` 與 `ks_root = {HKS_KS_ROOT_BASE}/{workspace_id}/`（目錄不存在則建立）。
2. 若 registry 無該 id：自動 `workspace register`（`label` 預設為 repo basename 原文）。
3. 若 id 已存在但 `ks_root` 不同且未 `--force`：回傳衝突錯誤（沿用 012 exit `66` 語意）。
4. 在解析後之 `KS_ROOT` 執行 ingest pipeline。

### 2.4 Task-end ingest 流程

```text
Agent (task end)
  → MCP/HTTP: workspace_ingest_session_memory(workspace_id, path[, project_root])
  → Adapter (agent profile)
       1. 驗證 path 落在 {export_root}/{workspace_id}/
       2. 驗證來源為 session2memory（§3）
       3. 驗證 frontmatter workspace_id（若有）與請求一致
       4. auto-register（§2.3）
       5. ks ingest → wiki / graph / vector / page_tree / manifest
  → 回傳標準 success contract JSON
```

- **目錄 ingest**：子樹內 **任一檔案** 不符合 §3 則 **整批失敗**，不 partial commit。
- **session2memory** 不呼叫 HKS；寫檔完成即結束。

### 2.5 Query 流程

- 入口：`workspace_query(workspace_id, question, writeback=no)`（預設 `writeback=no`）。
- 內部：registry 解析 `KS_ROOT` → 既有 fused retrieval（wiki / graph / vector / page_tree）。
- Session-memory 日期 / workspace 意圖：沿用 `src/hks/routing/session_memory.py` 行為，範圍 **限該 workspace 的 `KS_ROOT`**。
- 結構化摘要：允許 `session_memory_summary`（日期區間 + 可選 workspace filter）。

---

## 3. Source Discipline

### 3.1 允許 ingest 的檔案

- 副檔名：`.md`（agent profile 下不 ingest 其他格式）。
- Frontmatter（YAML）**至少滿足其一**（建議兩者皆有）：
  - `generator: session2memory`
  - `source_domain: session_memory`
- 建議欄位（沿用現行 parser）：`hks_type`、`date`；session daily 另含 `workspace_id`、`memory_kind`、`tool`、`session_id`、`evidence_id` 等。

### 3.2 硬拒絕

以下情況 **必須失敗**（adapter error envelope + 明確 `code`），不得 silent skip：

- 路徑超出 `{export_root}/{workspace_id}/`
- 非 `.md` 或缺合格 frontmatter
- frontmatter `workspace_id` 與請求 `workspace_id` 不一致
- 目錄 ingest 中任一本不符合規則的檔案

### 3.3 與現行 general ingest 的關係

- CLI `ks ingest <path>` 與 full MCP `hks_ingest` **保留** 給本機 trusted 操作（fixtures、office 等）。
- **Agent profile** 不提供任意路徑 ingest；僅 `workspace_ingest_session_memory`。

---

## 4. Agent MCP/HTTP Surface

### 4.1 Profile 啟用

- `hks-mcp --profile agent` 或 `hks-api --profile agent`
- 環境變數：`HKS_AGENT_PROFILE=1`（與 flag 等價）

同一 binary；以 allowlist 切換 tool/endpoint，不改變 success/error JSON contract 形狀。

### 4.2 環境變數

| 變數 | 必填（agent） | 說明 |
|------|----------------|------|
| `HKS_SESSION2MEMORY_EXPORT_ROOT` | 是 | session2memory export 根目錄 |
| `HKS_KS_ROOT_BASE` | 是 | 各 workspace 的 `KS_ROOT` 父目錄 |
| `HKS_WORKSPACE_REGISTRY` | 否 | 覆寫 registry 路徑 |
| `HKS_API_TOKEN` | HTTP mutating 是 | Bearer token |
| `HKS_AGENT_PROFILE` | 否 | 啟用 agent allowlist |

預設綁定 **loopback**；非 loopback 需使用者明示（沿用現行 `hks-api` 政策）。

### 4.3 MCP tools（agent profile 允許）

| Tool | 用途 |
|------|------|
| `hks_workspace_query` | 主查詢；必填 `workspace_id`；`writeback` 預設 `no` |
| `hks_workspace_ingest_session_memory` | Task-end ingest；必填 `workspace_id`、`path`；可選 `project_root` 供 id 驗證 |
| `hks_workspace_show` | 顯示 registry 紀錄與狀態 |
| `hks_workspace_list` | 列出 workspaces |
| `hks_session_memory_summary` | 日期區間結構化摘要；必填 `workspace_id` |
| `hks_source_list` | 唯讀 catalog（當前 workspace 的 `KS_ROOT`） |
| `hks_source_show` | 唯讀單一 source |

### 4.4 MCP tools（agent profile 不暴露）

- `hks_ingest`（任意路徑）、無 `workspace_id` 的 `hks_query`
- `hks_workspace_register` / `hks_workspace_remove`（register 由首次 ingest 自動完成；remove 僅 CLI）
- `hks_lint`（agent 路徑不暴露；必要時日後另開 read-only lint）
- `hks_graphify_*`、`hks_watch_*`、`hks_coord_*`
- `hks_llm_classify`、`hks_wiki_synthesize`、`hks_pageindex_enrich`
- full profile 其餘 mutating / derived tools

### 4.5 HTTP endpoints（agent profile）

**允許**

| Method | Path | 對應語意 |
|--------|------|----------|
| `POST` | `/workspaces/{workspace_id}/query` | workspace query |
| `POST` | `/workspaces/{workspace_id}/ingest/session-memory` | task-end ingest |
| `POST` | `/session-memory/summary` | body 含 `workspace_id`、日期區間 |
| `POST` | `/catalog/sources` | workspace-scoped source list |
| `POST` | `/catalog/sources/{relpath}` | workspace-scoped source show |
| `GET` | `/workspaces` | list |
| `GET` | `/workspaces/{workspace_id}` | show |

**拒絕**（HTTP `403`，`code: AGENT_PROFILE_FORBIDDEN`；contract test 鎖定此行為）

- 通用 `POST /ingest`
- 無 workspace 的 `POST /query`
- `/watch/*`、`/graphify/*`、`/coord/*`、`/llm/*`、`/wiki/*` 等 full-profile 專用路由

Ingest body：`path`（相對 `{export_root}/{workspace_id}/` 或該子樹內絕對路徑）、可選 `prune`。**不接受** body 內 `ks_root` override。

### 4.6 驗證與信任

- **HTTP**：`Authorization: Bearer $HKS_API_TOKEN`；mutating 必填。
- **MCP stdio**：本機信任（與現行一致）。
- **MCP streamable-http**：同 HTTP Bearer 規則。
- **Agent skill 契約**：task-end 僅呼叫 `workspace_ingest_session_memory`；日常查詢用 `workspace_query`。

### 4.7 消費端

Cursor、Codex、Claude、OpenClaw **共用同一 agent profile 契約**（ingest + query）。

---

## 5. 錯誤處理

Adapter 錯誤使用既有 envelope：

```json
{"ok":false,"error":{"code":"...","exit_code":1,"message":"...","details":{}},"response":{}}
```

| `code` | 情境 | 建議 `exit_code` |
|--------|------|------------------|
| `WORKSPACE_PATH_OUT_OF_ROOT` | ingest path 不在 export 子樹 | 65（DATAERR） |
| `INGEST_SOURCE_DISALLOWED` | 非 session2memory 或缺 frontmatter | 65 |
| `WORKSPACE_ID_MISMATCH` | frontmatter `workspace_id` ≠ 請求 | 65 |
| `WORKSPACE_ID_INVALID` | slug 規則不符 | 64（USAGE） |
| `WORKSPACE_NOT_READY` | auto-register 失敗或 `KS_ROOT` 不可用 | 66（NOINPUT） |
| `AGENT_PROFILE_FORBIDDEN` | 呼叫 hidden tool/endpoint | 64 |
| （既有）workspace 衝突 | id 已存在且 `ks_root` 不同 | 66 |

`message` / `hint` 使用 zh-TW；`code` 與欄位名維持 English。

---

## 6. 測試策略

### 6.1 Contract tests

- Agent profile MCP tool manifest 與 full profile diff（允許集合固定）。
- HTTP route 表：agent profile 下 forbidden routes 回傳預期 `code`。
- Ingest/query request schema：`workspace_id` 必填、禁止 `ks_root` override（agent paths）。

### 6.2 Integration tests

- 合法 `{export_root}/{workspace_id}/daily/*.md` ingest → manifest + metadata 傳播（沿用 session2memory 既有測試語意）。
- 拒絕：harness 假 `.md`、錯誤子目錄、frontmatter `workspace_id` 不一致、目錄內夾雜非合格檔（整批失敗）。
- 首次 ingest auto-register → 同 `workspace_id` query 可命中。
- Full profile regression：`ks ingest tests/fixtures`、既有 MCP tools 不受 agent profile 影響。

### 6.3 文件與 skill

- 更新 `mcp/README.md`、`mcp/tools/hks-mcp-tools.json`（agent 條目）
- 更新 `skill/hks-knowledge-system`：agent task-end ingest、env 範本
- `docs/main.md` 增補 agent integration 小節（與本 spec 連結）
- 提供 env 範例片段（不提交 secrets）

---

## 7. Rollout

1. 實作 agent profile allowlist + `workspace_ingest_session_memory`（MCP + HTTP）。
2. 實作 export 路徑與 source discipline 驗證層（adapter 內，委派既有 ingest）。
3. 補 contract / integration tests（§6）。
4. 更新 agent-facing 文件與 skill；標明 harness transcript **永不**進 HKS。

---

## 8. 已鎖定決策清單

| 主題 | 決策 |
|------|------|
| HKS 定位 | 僅 query + 沉澱專案知識；不碰 harness |
| 來源 | 僅 session2memory 產物；不符合硬拒絕 |
| Ingest 觸發 | Coding agents + OpenClaw 任務結束經 MCP/HTTP（B） |
| Workspace | `{export_root}/{workspace_id}/`；id = slugified repo basename（A） |
| `KS_ROOT` | 每 workspace 一個；首次 ingest auto-register |
| 參數 | ingest/query 強制 `workspace_id` |
| 介面 | Approach 1：agent profile on `hks-mcp` / `hks-api` |
| OpenClaw | 與 Cursor/Codex/Claude 相同 ingest + query（B） |

---

## 9. 實作後續

使用者審閱本 spec 並確認後，依 **writing-plans** skill 產出實作計畫（`specs/0XX-*` 或 `docs/superpowers/plans/` 慣例由計畫階段決定）。
