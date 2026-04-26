# Tasks: Phase 3 階段一 — 影像 ingest（OCR）

**Input**: Design documents from `/specs/004-phase3-image-ingest/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

## Phase 1: Setup

- [X] T001 建立 `spec.md` clarify 決策，凍結 OCR engine / VLM 邊界 / 支援格式 / wiki body 表現
- [X] T002 以 `setup-plan.sh` 建立 `plan.md`，並補齊 `research.md` / `data-model.md` / `quickstart.md` / `contracts/`

## Phase 2: Foundational

- [X] T003 擴充 `src/hks/core/manifest.py` 支援 `png` / `jpg` / `jpeg` 的 suffix + magic sniffing
- [X] T004 擴充 `src/hks/ingest/guards.py` 與 `src/hks/ingest/fingerprint.py`，加入 image timeout / file size / pixel limit / OCR fingerprint
- [X] T005 新增 `src/hks/ingest/ocr.py` 與 `src/hks/ingest/parsers/image.py`
- [X] T006 擴充 `src/hks/ingest/models.py`、`office_common.py`、`normalizer.py`，納入 `ocr_text` / `ocr_empty` / OCR metadata
- [X] T007 擴充 `src/hks/ingest/pipeline.py`、`src/hks/commands/ingest.py`、`src/hks/commands/query.py`、`src/hks/cli.py`、`src/hks/core/ingest_contract.py`

## Phase 3: User Story 1 - Image ingest to wiki/vector/graph

- [X] T010 新增 `tests/fixtures/build_images.py`，生成 valid/broken image fixtures
- [X] T011 新增 `tests/unit/test_parser_image.py`
- [X] T012 新增 `tests/integration/test_image_pipeline.py`

## Phase 4: User Story 2 - Query consumes image-derived knowledge

- [X] T020 新增 `tests/integration/test_query_image_hits.py`
- [X] T021 擴充 `tests/contract/test_json_schema.py`，驗證 image vector trace metadata 仍符合既有 contract
- [X] T022 擴充 `tests/integration/test_offline.py`，驗證 image ingest/query 不需網路

## Phase 5: User Story 3 - Safe degradation

- [X] T030 新增 `tests/integration/test_image_degradation.py`
- [X] T031 擴充 `tests/contract/test_exit_codes.py` 與 `tests/contract/test_ingest_summary_detail_schema.py`
- [X] T032 擴充 `tests/unit/test_format_detection.py` / `tests/unit/test_office_guards.py` / `tests/unit/test_manifest_fingerprint.py`

## Phase 6: Polish

- [X] T040 更新 `README.md` / `README.en.md` / `docs/main.md` / `docs/PRD.md`
- [X] T041 跑 `./.specify/scripts/bash/check-prerequisites.sh --json --include-tasks --require-tasks`
- [X] T042 跑 `uv run pytest -q`、`uv run ruff check .`、`uv run mypy src/hks`

## Notes

- `004` 不引入 VLM。
- `004` 不支援 `.heic` / `.webp`。
- 0 byte 檔案的 skip reason 維持 `empty_file`，與現有 runtime 對齊。
