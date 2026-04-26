# Implementation Plan: Phase 2 階段二 — Graph Query、Model-Driven Routing、Auto Write-back

**Branch**: `003-phase2-graph-routing` | **Date**: 2026-04-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-phase2-graph-routing/spec.md`

## Summary

在不引入 hosted API 的前提下，把剩餘 Phase 2 runtime 補齊：新增 JSON-backed graph layer、relation extractor、graph query、semantic routing backend、以及以 confidence threshold 驅動的 auto write-back；同時翻掉 Phase 1 的 no-graph 契約測試，改為 Phase 2 contract。

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`（沿用）
**Primary Dependencies**: 既有 `typer`、`chromadb`、`sentence-transformers`、`jsonschema`；不新增 graph DB、不新增 hosted LLM SDK
**Storage**: `/ks/raw_sources/`、`/ks/wiki/`、`/ks/graph/graph.json`、`/ks/vector/db/`、`/ks/manifest.json`
**Testing**: `pytest` + `ruff` + `mypy strict`
**Target Platform**: macOS / Linux CLI，離線可跑
**Project Type**: 單一 Python CLI package
**Performance Goals**: query p95 維持 < 3s；graph lookup 不得明顯拖慢既有 fixture 規模
**Constraints**: local-first、穩定 JSON contract、re-ingest / prune 不留髒 graph
**Scale/Scope**: fixture 等級 graph（數十 nodes / edges）先穩定，Phase 3 再談更重推理

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **§II Stable Output Contract**：PASS。只擴充 `graph` enum 與新 trace kinds，不改 top-level shape。
- **§IV Ingest-Time Organization**：PASS。graph 抽取仍在 ingest 階段完成，query 不會 re-parse source files。
- **§V Write-back Safety**：PASS。auto write-back 以明確 threshold 與可觀測 log 控制，`--writeback=no` 仍可硬關閉。

## Project Structure

### Documentation (this feature)

```text
specs/003-phase2-graph-routing/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── query-response.schema.json
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── graph/
│   ├── store.py
│   ├── extract.py
│   └── query.py
├── commands/query.py
├── ingest/pipeline.py
├── routing/
│   ├── router.py
│   └── rules.py
├── writeback/
│   ├── gate.py
│   └── writer.py
└── core/
    ├── schema.py
    ├── paths.py
    └── manifest.py

tests/
├── contract/
├── integration/
└── unit/
```

**Structure Decision**：沿用既有單一 CLI package；graph 僅新增 `src/hks/graph/` 子套件，不另立 service。

## Complexity Tracking

無違反。Constitution Check 全數 PASS，毋須列舉豁免。

## Post-Design Re-Check

設計產出（`research.md` / `data-model.md` / `contracts/` / `quickstart.md`）完成後重新對照憲法與 cross-artifact 一致性：

- **§II Stable Output Contract**：`contracts/query-response.schema.json` 僅把 `source` / `trace.route` 擴充為允許 `graph`，top-level 仍維持 `answer / source / confidence / trace` 四欄；`ks ingest`、`ks query`、`ks lint` 的共用 shape 與 [docs/main.md](../../docs/main.md) / [README.md](../../README.md) 一致。**PASS**。
- **§III CLI-First & Domain-Agnostic**：`spec.md` clarify 後明確凍結 `003` 不新增 ingest 格式；Phase 2 的格式全集維持 `txt / md / pdf / docx / xlsx / pptx`。圖片 ingest 仍在後續 Phase 3 spec，但 exact raster format set 與 normalize / 轉檔策略尚未凍結。此邊界與 [docs/main.md](../../docs/main.md)、[docs/PRD.md](../../docs/PRD.md)、[README.md](../../README.md)、[README.en.md](../../README.en.md) 一致。**PASS**。
- **§IV Ingest-Time Organization**：graph extraction 仍在 ingest 階段完成，`data-model.md` 與 `research.md` 都以 `graph.json`、manifest derived artifacts、re-ingest cleanup 為中心；`003` 沒有偷偷新增新的 source format 或 query-time re-parse。**PASS**。
- **§V Write-back Safety**：`spec.md` clarify 後把 `auto` write-back 的 automation 邊界寫死：runtime 預設 `auto`，但 CI / smoke / agent workflow 以顯式 `--writeback=no` 關閉；non-TTY 不得因互動邏輯阻塞。此行為與 [quickstart.md](./quickstart.md) 及 README 敘述一致。**PASS**。
- **Analyze 結論**：未發現要求把圖片 ingest 提前到 `003` 的 artifact；`003` 補的是 graph / routing / auto write-back，不是新一輪格式擴充。`001` + `002` + `003` 合起來才構成完整 Phase 2；圖片格式與 normalize 策略留待後續 spec。**PASS**。

**Post-Design 結果**：全數 PASS。`003` 的 speckit artifact 鏈現已包含 clarify 與 analyze 的留痕，可維持 `Status: Complete`。
