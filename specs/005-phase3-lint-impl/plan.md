# Implementation Plan: Phase 3 階段二 — `ks lint` 真實實作

**Branch**: `005-phase3-lint-impl` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-phase3-lint-impl/spec.md`

## Summary

把 Phase 1 的 `ks lint` stub 換成 deterministic、local-first 的跨層一致性檢查。實作以新 `hks.lint` domain 模組讀取 `manifest.json`、`wiki/`、`vector/db/`、`graph/graph.json` 與 `raw_sources/`，產出 `Finding` / `FixAction` / `FixSkip`，再由 `src/hks/commands/lint.py` 包裝成既有 `QueryResponse` top-level JSON。`--strict` 只改 exit code，不改 stdout；`--fix` 預設 dry-run，`--fix=apply` 僅執行許可清單內的 rebuild/prune 動作，且逐筆寫入 `wiki/log.md` audit log。

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`
**Primary Dependencies**:
- 沿用既有 `typer`：CLI flags 與 usage error
- 沿用既有 `jsonschema`：`lint_summary.detail` runtime validation
- 沿用既有 `chromadb`：列出 / 刪除 vector chunk ids
- 沿用既有 `python-slugify` / markdown frontmatter parser：wiki slug / page 讀取
**Storage**: `/ks/raw_sources/`、`/ks/wiki/{index.md,log.md,pages/}`、`/ks/graph/graph.json`、`/ks/vector/db/`、`/ks/manifest.json`
**Testing**: `pytest` + `pytest-cov` + `ruff` + `mypy strict`
**Target Platform**: macOS / Linux CLI；無網路需求
**Project Type**: 單一 Python CLI package
**Performance Goals**: read-only lint 對 50 份混合文件 + 10 份影像 < 5s；`--fix=apply` < 10s
**Constraints**:
- 不新增 `source` / `trace.route` enum
- `trace.steps.kind` 僅新增 `lint_summary`
- 不呼叫 LLM / hosted API / 對外網路
- 不觸發 re-ingest、不修改 `manifest.json`
- `--fix=apply` 不刪 `wiki/pages/*.md`、不刪 `raw_sources/*`
**Scale/Scope**:
- 11 個 finding category：`orphan_page` / `dead_link` / `duplicate_slug` / `manifest_wiki_mismatch` / `wiki_source_mismatch` / `dangling_manifest_entry` / `orphan_raw_source` / `manifest_vector_mismatch` / `orphan_vector_chunk` / `graph_drift` / `fingerprint_drift`
- 4 個 apply action：`rebuild_index` / `prune_orphan_vector_chunks` / `prune_orphan_graph_nodes` / `prune_orphan_graph_edges`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **§I Phase Discipline**：PASS。005 只做 Phase 3 lint system；MCP adapter（006）與 multi-agent（007）不碰。
- **§II Stable Output Contract**：PASS。top-level `QueryResponse` 不變；`trace.steps.kind` 新增 `lint_summary` 屬 MINOR 擴充，並由 contract schema 固化。
- **§III CLI-First & Domain-Agnostic**：PASS。入口仍是 `ks lint`；無 UI、service、domain-specific rule。
- **§IV Ingest-Time Organization**：PASS。lint 只讀 ingest-time 已整理的四層資料；`--fix=apply` 不 re-ingest、不重算 parser output。
- **§V Write-back Safety**：PASS。lint 不改 query write-back；唯一寫入是明確 opt-in 的 `--fix=apply` audit log 與許可清單修復。

## Project Structure

### Documentation (this feature)

```text
specs/005-phase3-lint-impl/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── query-response.schema.json
│   └── lint-summary-detail.schema.json
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py
├── commands/
│   └── lint.py
├── core/
│   ├── lint_contract.py
│   ├── lock.py
│   ├── manifest.py
│   └── schema.py
├── graph/
│   └── store.py
├── lint/
│   ├── __init__.py
│   ├── checks.py
│   ├── fixer.py
│   ├── models.py
│   └── runner.py
└── storage/
    ├── vector.py
    └── wiki.py

tests/
├── contract/
│   ├── test_exit_codes.py
│   ├── test_json_schema.py
│   ├── test_lint_contract.py
│   └── test_lint_stub.py
├── integration/
│   ├── test_lint_findings.py
│   ├── test_lint_fix.py
│   └── test_lint_strict.py
└── unit/
    └── lint/
        ├── test_checks.py
        ├── test_fixer.py
        └── test_runner.py
```

**Structure Decision**: 沿用單一 Python CLI package。lint 獨立放在 `src/hks/lint/`，避免把 read-only consistency check 混進 ingest pipeline；storage 層只補必要的 list/prune helper，不改 ingest/query 行為。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| （無） | — | — |

## Phase 0: Research

已輸出 [research.md](./research.md)，決策重點：

- lint runner 採 snapshot + pure checks，避免 checks 直接寫入資料層。
- `--fix=apply` 先重新計算同一批 fix plan，再逐 action apply。
- lock 採既有 `file_lock(paths.lock)` non-blocking exclusive 行為；取不到鎖 exit `1`。
- vector listing 以 Chroma collection `get()` 讀取 ids；封裝在 `VectorStore.list_ids()`。

## Phase 1: Design & Contracts

已輸出：

- [data-model.md](./data-model.md)：`Finding` / `FixAction` / `FixSkip` / `LintSummaryDetail` / `LintRunMode`
- [contracts/query-response.schema.json](./contracts/query-response.schema.json)：Phase 3 CLI response schema，僅擴 `trace.steps.kind=lint_summary`
- [contracts/lint-summary-detail.schema.json](./contracts/lint-summary-detail.schema.json)：`trace.steps[kind=lint_summary].detail` 的權威 schema
- [quickstart.md](./quickstart.md)：clean lint、人工注入 findings、strict、fix dry-run/apply、error path 驗證

## Post-Design Re-Check

- **§I**：`research.md` / `tasks.md` 明確排除 006 MCP adapter 與 007 multi-agent。**PASS**
- **§II**：`query-response.schema.json` 僅新增 `lint_summary`，`source` / `trace.route` 未擴；`lint-summary-detail.schema.json` 封裝 detail。**PASS**
- **§III**：無 UI / service / cloud dependency。**PASS**
- **§IV**：`data-model.md` 把 scan/fix 分離；fix 不觸發 re-ingest。**PASS**
- **§V**：log 新增 event `lint` / status `lint_fix_applied`，不改 query write-back。**PASS**
