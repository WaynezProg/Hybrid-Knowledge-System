# Quickstart: Phase 3 階段一 — 影像 ingest（OCR）

## 1. Local setup

```bash
brew install tesseract tesseract-lang
uv sync
```

確認 OCR backend：

```bash
tesseract --version
tesseract --list-langs | rg 'eng|chi_tra'
```

## 2. Build fixtures

```bash
uv run python tests/fixtures/build_images.py
```

輸出：

- `tests/fixtures/valid/image/`
- `tests/fixtures/broken/image/`

## 3. Ingest image fixtures

```bash
export KS_ROOT=/tmp/hks-image
uv run ks ingest tests/fixtures/valid/image
```

預期：

- `raw_sources/` 只會有 5 份 image 原檔（`no-text.png` 走 `ocr_empty` skip）
- `wiki/pages/` 有 5 頁
- `manifest.json` 的 image entries 帶 `parser_fingerprint`

## 4. Query image-derived content

```bash
uv run ks query "summary atlas dependency" --writeback=no
uv run ks query "detail Owner Iris" --writeback=no
uv run ks query "Atlas 依賴什麼" --writeback=no
```

預期：

- summary 類走 `wiki`
- detail 類走 `vector`
- relation 類走 `graph`
- `source` / `trace.route` 不會出現 `image` / `ocr`

## 5. Degradation smoke

```bash
export HKS_IMAGE_TIMEOUT_SEC=1
export HKS_IMAGE_MAX_FILE_MB=1
uv run pytest tests/integration/test_image_degradation.py -q
```

## 6. Full verification

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src/hks
```
