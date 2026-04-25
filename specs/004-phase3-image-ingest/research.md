# Research: Phase 3 階段一 — 影像 ingest（OCR）

## 1. OCR engine 候選

| 候選 | 結論 | 理由 |
|---|---|---|
| `tesseract` CLI + `tesseract-lang` | 採用 | 本機可執行、license 清楚、Homebrew 可裝、`eng+chi_tra` 對 zh-TW/English fixture 足夠 |
| `pytesseract` | 不採用 | 只是 Python wrapper；本 repo 直接呼叫 CLI 更少依賴、錯誤面更小 |
| PaddleOCR / EasyOCR | 不採用 | 額外重量級模型依賴與下載面太大，不利 airgapped 與 CI 穩定性 |
| Hosted OCR/VLM API | 禁用 | 違反 local-first 與 `004` 邊界 |

## 2. Clarify 決策落點

- OCR engine：`tesseract` CLI，預設 `HKS_OCR_LANGS=eng+chi_tra`
- VLM：不進 MVP，不提供 `--vlm`
- `.heic` / `.webp`：不進 `004`
- 影像 wiki body：放 OCR 全文，不只存摘要
- 0 byte 空檔：沿用既有 `empty_file`

## 3. Decode / preprocess

- Decode：Pillow
- Orientation：`ImageOps.exif_transpose`
- Preprocess：`convert("L")` + `ImageOps.autocontrast`
- `parser_fingerprint`：`{format}:v{Pillow}:{preprocess_signature}:{tesseract+langs}:off`

## 4. OCR block 粒度

- 以 tesseract TSV 的 line group（`block_num/par_num/line_num`）為最小 segment
- segment kind = `ocr_text`
- 每個 segment metadata 帶：
  - `ocr_confidence`
  - `source_engine`
  - `bbox_left/top/width/height`
- vector chunk 以 line 為界，不把 image OCR 重新合併成大段，這樣 query 命中的 confidence 與 bbox 仍可追

## 5. 錯誤與降級語意

- `corrupt`：magic 不符或 Pillow decode 失敗
- `oversized`：原始檔大小超過 `HKS_IMAGE_MAX_FILE_MB`
- `timeout`：整檔 parse + OCR 超過 `HKS_IMAGE_TIMEOUT_SEC`
- `empty_file`：0 byte
- `ocr_empty`：成功 decode/OCR 但沒有任何可辨識文字；skip，不算 failure

## 6. Local-first 驗證

- 本機已驗證 `tesseract 5.5.2` 可執行
- 補裝 `tesseract-lang` 後可用 `chi_tra`
- probe image 對 `Atlas 狀態：正常 / 供應商延遲 3 天 / Mobile Gateway affected` 可正確辨識；因此 `eng+chi_tra` 足夠支撐 fixture 與 regression tests
