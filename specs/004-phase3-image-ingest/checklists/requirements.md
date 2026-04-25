# Specification Quality Checklist: Phase 3 階段一 — 影像 ingest（OCR）

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Focused on user value and business needs
- [x] All mandatory sections completed
- [x] Clarify 決策已明寫，scope 與 non-goals 可直接判讀
- [x] 技術細節只出現在已凍結的 local-first / OCR 邊界，不再自撞

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows 與 degradation
- [x] `spec.md` / `plan.md` / `tasks.md` 一致指向 OCR-only，不存在偷放 `--vlm`
- [x] query top-level schema 維持 `wiki|graph|vector`；image 專屬欄位只落在既有 detail / metadata
- [x] image fingerprint、offline、degradation 契約已有對應測試與文件落點

## Notes

- `/speckit.clarify` 決議已寫回 `spec.md`：`tesseract`、無 VLM、`.heic/.webp` 不納入、wiki body 放 OCR 全文、0 byte reason 維持 `empty_file`
- `/speckit.analyze` 結論：
  - `spec.md` / `plan.md` / `tasks.md` 都一致指向 OCR-only，不存在偷放 `--vlm`
  - runtime contract 以 `specs/004-phase3-image-ingest/contracts/ingest-summary-detail.schema.json` 為 ingest summary 單一權威
  - query top-level schema 仍沿用 `003`，只允許既有 `wiki|graph|vector`
  - degradation 測試改以 4 份 broken/degradation fixtures + 1 份 valid `no-text.png` 驗證 `ocr_empty`，不再把 `no-text` 寫成 broken fixture
