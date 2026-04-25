# Implementation Plan: Phase 3 階段一 — 影像 ingest（OCR）

**Branch**: `004-phase3-image-ingest` | **Date**: 2026-04-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-phase3-image-ingest/spec.md`

## Summary

把 Phase 2 的 ingest pipeline 擴充到三種獨立影像格式：`.png` / `.jpg` / `.jpeg`。parser 以 Pillow 做 decode + EXIF transpose + grayscale/autocontrast preprocess，再交給本機 `tesseract` CLI（預設 `eng+chi_tra`）做 OCR，輸出 line-based `ocr_text` segments，沿用既有 `parse → normalize → extract → update(wiki, vector, graph)` 四階段，不另立平行流程。VLM 不進 MVP；`.heic` / `.webp` 也不進。`ks query` top-level schema 完全不變，僅透過既有 wiki / graph / vector route 消費 image-origin 的內容。

## Technical Context

**Language/Version**: Python `>=3.12,<3.13`
**Primary Dependencies**:
- `Pillow`：decode、EXIF orientation、preprocess、fixture 生成
- 本機 `tesseract` + `tesseract-lang`：OCR engine，預設使用 `eng+chi_tra`
- 沿用既有 `typer` / `chromadb` / `sentence-transformers` / `jsonschema`
**Storage**: `/ks/raw_sources/`、`/ks/wiki/`、`/ks/graph/graph.json`、`/ks/vector/db/`、`/ks/manifest.json`
**Testing**: `pytest` + `ruff` + `mypy strict`
**Target Platform**: macOS / Linux CLI；OCR 依賴本機 `tesseract`
**Project Type**: 單一 Python CLI package
**Performance Goals**: 單檔影像 OCR soft timeout 30s；query p95 維持 < 3s；第二次 re-ingest 因 hash/fingerprint skip 顯著加速
**Constraints**:
- local-first，query 不得在 runtime 觸發 OCR
- `source` / `trace.route` enum 不擴
- `.heic` / `.webp` / gif / tiff / svg 不在 004
- 0 byte 空檔維持既有 skip reason `empty_file`
**Scale/Scope**:
- valid fixtures 6 份（含無文字純圖）
- broken fixtures 4 份（corrupt / oversized / timeout / empty）
- mixed ingest regression：Phase 1 + 2 + image 共存，不破壞既有 route/source 契約

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **§I Phase Discipline**：PASS。只做 Phase 3 的 image ingest；`lint`、MCP、multi-agent 不碰。
- **§II Stable Output Contract**：PASS。`ks query` 與 `ks ingest` top-level JSON shape 不變；僅擴充 `ingest_summary.detail.files[]` 的 file report 欄位。
- **§III CLI-First & Domain-Agnostic**：PASS。入口仍為 `ks` CLI；OCR engine 為本機工具，無 UI / service / hosted API。
- **§IV Ingest-Time Organization**：PASS。OCR 在 ingest-time 完成；query 只讀 wiki / vector / graph。
- **§V Write-back Safety**：PASS。write-back 行為不改。

## Project Structure

### Documentation (this feature)

```text
specs/004-phase3-image-ingest/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── ingest-summary-detail.schema.json
│   └── image-runtime-env.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hks/
├── cli.py
├── commands/
│   ├── ingest.py
│   └── query.py
├── core/
│   ├── ingest_contract.py
│   └── manifest.py
├── ingest/
│   ├── fingerprint.py
│   ├── guards.py
│   ├── models.py
│   ├── normalizer.py
│   ├── ocr.py
│   ├── office_common.py
│   ├── pipeline.py
│   └── parsers/
│       └── image.py
└── storage/ / graph/ / routing/

tests/
├── contract/
├── integration/
├── unit/
└── fixtures/
    ├── valid/image/
    └── broken/image/
```

**Structure Decision**: 沿用既有單一 Python CLI package。影像邏輯只新增 `ingest/ocr.py` 與 `parsers/image.py`，其餘透過既有 pipeline / manifest / contract 擴充完成。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| （無） | — | — |

## Post-Design Re-Check

- `research.md` 已凍結 OCR engine = `tesseract`，並把 VLM / `.heic` / `.webp` 明確排除。`plan`、`spec`、`tasks` 一致。**PASS**
- `data-model.md` 把新增欄位限制在 `ingest_summary.detail.files[]` 與 vector chunk metadata，不碰 query top-level schema。**PASS**
- `contracts/ingest-summary-detail.schema.json` 與 runtime `src/hks/core/ingest_contract.py` 已同步指向 `004`。**PASS**
- `quickstart.md` 以 `brew install tesseract tesseract-lang` 明寫本機 setup；offline smoke 可在 airgapped 下跑。**PASS**
