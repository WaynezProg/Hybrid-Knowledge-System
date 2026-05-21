# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Repository status

此 repo 已有完整 Python runtime，Phase 1-3 均已完成並 merge 到 `main`。目前不是 pre-implementation repo。

權威來源：

- [docs/main.md](docs/main.md) - 系統設計、runtime layout、routing/write-back/coordination 契約
- [README.md](README.md) - 使用者面中文 onboarding 與實際指令
- [README.en.md](README.en.md) - 使用者面英文 onboarding
- [docs/PRD.md](docs/PRD.md) - 產品目標、persona、roadmap 狀態
- [specs/ARCHIVE.md](specs/ARCHIVE.md) - 已完成 spec 索引

三者敘述不一致時，以 [docs/main.md](docs/main.md) 為架構準則，以 runtime code / tests 為行為事實。封存 spec 原則上只做勘誤、連結修補或 post-merge 註記；新功能或契約變更請走新的 `specs/0XX-*`。

## Stack & commands

專案已 scaffold，CLI 與 adapter entry points 已在 [pyproject.toml](pyproject.toml) 宣告：

```toml
ks = "hks.cli:app"
hks-mcp = "hks.adapters.mcp_server:main"
hks-api = "hks.adapters.http_server:main"
```

常用指令：

```bash
uv sync
uv run ks --help
uv run ks ingest <path>
uv run ks query "<q>"
uv run ks lint
uv run ks coord status
uv run hks-mcp --help
uv run hks-api --help
uv run pytest
uv run ruff check .
uv run mypy src/hks
```

## Architecture

系統是 local-first、CLI-first、domain-agnostic 的知識系統，三層知識儲存由 ingestion pipeline 同步：

```text
Agent / MCP / HTTP -> ks / adapter -> Core
                                      ├── wiki   (/ks/wiki/{index.md,log.md,pages/})
                                      ├── graph  (/ks/graph/graph.json)
                                      ├── vector (/ks/vector/db/)
                                      └── coordination (/ks/coordination/{state.json,events.jsonl})
raw_sources (immutable) -> ingestion -> wiki + graph + vector + manifest
```

關鍵契約：

- **Ingestion 是寫入時整理**：parse -> normalize -> extract -> update，同步更新 `raw_sources`、`wiki`、`graph`、`vector`、`manifest`。
- **Query 走 fused retrieval**：同時從 wiki / graph / vector / page_tree 收集 candidates，以 LLM reranker 排序（無 API key 時 fallback RRF）；response 含 `evidence[]` 溯源。
- **Write-back 預設 auto**：`confidence >= HKS_WRITEBACK_AUTO_THRESHOLD` 時自動寫回 wiki；agent / CI workflow 若不想產生頁面請顯式帶 `--writeback=no`。
- **Lint 已不是 stub**：`ks lint` 檢查跨層一致性；`--strict` 控制 exit code；`--fix=apply` 只執行 allowlist 修復。
- **MCP / HTTP adapter 已是正式介面**：`hks-mcp` 與 `hks-api` 不再是非目標。

## Stable contracts

`ks ingest`、`ks query`、`ks lint`、`ks coord` 與 adapter 成功 payload 共用 top-level JSON shape：

```json
{"answer":"...","source":["wiki"],"confidence":0.88,"evidence":[{"source_relpath":"atlas.txt","route":"wiki","quote":"..."}],"trace":{"route":"wiki","steps":[]}}
```

Adapter 錯誤 payload 使用：

```json
{"ok":false,"error":{"code":"...","exit_code":1,"message":"...","details":{}},"response":{}}
```

任何欄位、exit code、route 名稱、trace step schema 的變更都是對外 API 變更，需補 contract tests。

## Phase discipline

Phase 1-3 已完成；現在的重點是避免回歸，不是阻止已完成能力存在。

| Spec | Status | Runtime contract |
|---|---|---|
| `001-phase1-cli-mvp` | archived | `txt / md / pdf` ingest、wiki + vector、CLI baseline、半自動 write-back compatibility |
| `002-phase2-ingest-office` | archived | `docx / xlsx / pptx` ingest、Office parser guardrails |
| `003-phase2-graph-routing` | archived | graph extraction/query、model-driven routing、auto write-back |
| `004-phase3-image-ingest` | archived | `png / jpg / jpeg` OCR ingest |
| `005-phase3-lint-impl` | archived | real `ks lint` + strict/fix behavior |
| `006-mcp-api-adapter` | archived | `hks-mcp` + `hks-api` local adapter |
| `007-multi-agent-support` | archived | `ks coord` + coordination ledger |
| `008-llm-classification-extraction` | archived | `ks llm classify` + fake/openai provider + extraction artifacts |
| `009-llm-wiki-synthesis` | archived | `ks wiki synthesize` preview/store/apply + wiki candidate artifacts |
| `010-graphify-pipeline` | archived | `ks graphify build` derived graph + HTML + communities + audit |
| `011-continuous-watch` | archived | `ks watch scan/run/status` bounded refresh |
| `012-source-catalog` | archived | `ks source` 唯讀 catalog + `ks workspace` 註冊/查詢多 `KS_ROOT` |

不要把現有 graph、auto write-back、lint、MCP/API、coordination、LLM extraction、wiki synthesis、graphify、watch 當成越界刪除。修改這些行為時，請更新對應 docs、contract tests 與 runtime tests。

## Graph schema

穩定最小集合，擴充前需更新 [docs/main.md](docs/main.md) 與 contract tests：

- Entity：`Person` / `Project` / `Document` / `Event` / `Concept`
- Relation：`owns` / `depends_on` / `impacts` / `references` / `belongs_to`

## Non-goals

目前仍不做：

- UI
- 多使用者 / RBAC
- 雲端部署 / microservice
- 非文字素材（影片、音訊）

## Environment

主機 runtime 由 mise 管理；不要自行安裝 Python / Node runtime。需要 Python 版本變更時使用 `mise use python@<version>`，Python 套件使用 `uv`，系統工具才使用 Homebrew。

常用環境變數以 [README.md#設定](README.md#設定) 為準；完整說明見 [docs/configuration.md](docs/configuration.md)。不要在多份文件重複維護清單。

## Language

文件與 commit message 使用 Traditional Chinese（zh-TW）；程式碼、識別字、技術術語維持 English。

## Active Technologies
- Python `>=3.12,<3.13` + existing `typer`, `jsonschema`, `mcp`, `starlette`, `python-slugify`; `httpx` for OpenAI-compatible LLM calls
- 008 local JSON artifacts under `KS_ROOT/llm/extractions/`, separate from authoritative layers
- 009 local JSON candidate artifacts under `KS_ROOT/llm/wiki-candidates/`; applied pages update `wiki/` only in explicit apply mode
- 010 derived artifacts under `$KS_ROOT/graphify/runs/<run-id>/`; latest pointer under `$KS_ROOT/graphify/latest.json`; no writes to authoritative layers
- 011 operational artifacts under `$KS_ROOT/watch/{plans,runs,latest.json,events.jsonl,config.json}`; no new authoritative layer
- 012 read-only source catalog over `manifest.json`; workspace registry persisted through `HKS_WORKSPACE_REGISTRY` / XDG config, not inside `KS_ROOT`

## Recent Changes
- Fused retrieval: query 同時從 wiki / graph / vector / page_tree 收集 candidates，LLM reranker 排序（RRF fallback）；response 新增 `evidence[]` 溯源
- OpenAI-compatible LLM provider: env-gated `openai` provider for classify / synthesize / graphify / enrich
- Obsidian compatibility: frontmatter 全面 JSON-quoted，writeback link text escape `[]\`
- 012-source-catalog: `ks source list/show` + `ks workspace register/list/show/remove/use/query`
- 011-continuous-watch: bounded `ks watch scan/run/status`
- 010-graphify-pipeline: derived Graphify artifacts, communities, interactive HTML dashboard, audit report
- 009-llm-wiki-synthesis: `ks wiki synthesize` preview/store/apply
- 008-llm-classification-extraction: `ks llm classify` + fake/openai provider
