---
name: hks-knowledge-system
description: Operate the Hybrid Knowledge System through its main `ks` CLI. Use this skill for CLI-first HKS work: ingest, query, source catalog, workspace selection, lint, coordination, LLM extraction, wiki synthesis, Graphify, watch refresh, response contracts, mutation boundaries, and validation.
---

# HKS CLI Skill

## 使用時機

使用這個 skill 來操作 HKS repo 的主要 CLI surface。預設入口是 `ks`，不是 `hsk`。MCP / HTTP adapter 不放在這裡展開；需要 adapter 時讀 `mcp/README.md`。

## 先讀順序

1. `README.md`：skill 框架與檔案地圖
2. `commands/cli.md`：完整 `ks` command surface
3. `config/discover-runtime.sh`：先找出目前 workspace 內的 ignored local runtime
4. `workflows/persistent-workspace.md`：建立可重用的持久化 knowledge runtime
5. `config/shared-runtime.sh`：多 agent 共用同一個 repo-local runtime
6. `../../docs/configuration.md`：設定檔建立、欄位意義與驗證
7. `workflows/smoke-test.md`：最小驗證流程
8. `policies/safety.md`：mutation boundary 與環境規則
9. `contracts/response-contract.md`：JSON response contract

## 核心規則

- 從目前 clone 的 repo root 操作；不要寫死任何使用者本機絕對路徑。
- 使用 `uv run ...`；不要自行安裝 Python / Node runtime。
- 實驗一律顯式設定 `KS_ROOT`。
- 查詢預設用 `--writeback=no`，除非使用者要寫回 wiki。
- smoke test 用 `HKS_EMBEDDING_MODEL=simple`。
- OpenAI embedding 用 `config/hks.yaml` 設 `embedding.model=openai:text-embedding-3-small` 與 `embedding.openai.api_key`。
- 修改 code、contract 或 agent-facing docs 後，至少跑 `ks --help`、`ruff`、`mypy`；行為變更要跑 pytest。

## 最小安全流程

```bash
cd "$(git rev-parse --show-toplevel)"
export KS_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hks-agent.XXXXXX")"
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks query "這批資料的重點是什麼？" --writeback=no
uv run ks source list
uv run ks lint --strict
```

## 持久化 knowledge runtime

如果 agent 要跨 session 重用知識庫，不要只用 temporary `KS_ROOT`。先建立 repo-local runtime 並註冊 workspace：

```bash
sh skill/hks-knowledge-system/config/discover-runtime.sh
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks ingest <source-dir>
uv run ks workspace register work --ks-root "$KS_ROOT" --label "Work"
uv run ks workspace query work "目前有哪些資料？" --writeback=no
```

如果本機已有既有 runtime，將 `.hks-runs/shared-runtime.env` 指向那套 runtime；所有 agent source `shared-runtime.sh` 後會共用同一套。`HKS_EMBEDDING_MODEL` 必須跟該 runtime ingest 時使用的 model 一致，否則 vector query 會出現 dimension mismatch。

## Agent profile（session2memory task-end）

OpenClaw / Cursor / Codex / Claude 應使用 MCP/HTTP **agent profile**，只 ingest session2memory 產物（不 ingest harness transcript）：

```bash
export HKS_SESSION2MEMORY_EXPORT_ROOT="$HOME/session2memory/export"
export HKS_KS_ROOT_BASE="$HOME/.local/share/hks/workspaces"
export HKS_EMBEDDING_MODEL=simple
uv run hks-mcp --profile agent --transport stdio
```

Task-end：`hks_workspace_ingest_session_memory(workspace_id=<repo-basename>, path="daily/YYYY-MM-DD.md")`（路徑相對 `{export_root}/{workspace_id}/`）。日常查詢：`hks_workspace_query(..., writeback=no)`。

## Session Memory / Workspace Status Query

查詢 session memory 的 workspace 狀態時，**不要用口語名稱組寬鬆自然語言 query**。HKS 的 intent detection 對短詞、大小寫、alias 容易誤判，導致 retrieval 結果混入不相關條目。

### 正確流程

1. **先 resolve workspace_id**（不要跳過）：
   ```bash
   uv run ks workspace list              # 已註冊 workspace
   uv run ks source list                 # manifest 裡的 source metadata
   # 必要時 grep raw data：
   rg -n "workspace_id=" "$KS_ROOT/wiki/pages" "$KS_ROOT/raw_sources"
   ```

2. **用明確 workspace_id 查詢**：
   ```bash
   uv run ks query "workspace_id=<id> 最後處理到哪？" --writeback=no
   uv run ks query "workspace_id=<id> 最近完成什麼？" --writeback=no
   uv run ks query "workspace_id=<id> 2026-05-22 做了什麼？" --writeback=no
   ```

3. **預設 `--writeback=no`**。

### 禁止的做法

- **不要** 直接 `ks query "social-bank-check 最後處理到哪？"` — 口語名稱容易 miss 或 false-match。
- **不要** 依賴 HKS 猜測使用者說的 project 名稱對應哪個 workspace_id。

### Fallback

只有在所有 resolve 手段都找不到 workspace_id 時，才可以用自然語言 query 作 fallback，但 agent 必須在回覆中標記「信心較低，未能 resolve workspace_id」。

## 權威來源

- Architecture：`docs/main.md`
- User onboarding：`README.md`、`README.en.md`
- Product scope：`docs/PRD.md`
- Archived specs：`specs/ARCHIVE.md`
- Runtime truth：`src/hks/`、`tests/`

文件衝突時，以 runtime code / tests 為行為事實，以 `docs/main.md` 為架構準則。
