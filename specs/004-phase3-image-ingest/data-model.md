# Data Model: Phase 3 階段一 — 影像 ingest（OCR）

## 1. ParsedDocument 擴充

影像 parser 不新增新的 top-level runtime object；仍回傳既有 `ParsedDocument`：

```python
ParsedDocument(
  title: str,
  body: str,
  format: SourceFormat,
  segments: list[Segment],
  skipped_segments: list[SkippedSegment],
)
```

## 2. Segment

`Segment.kind` 新增 `ocr_text`。

每個 image OCR segment 的 metadata：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `ocr_confidence` | `float` | `[0,1]`，取該 line 的平均 word confidence |
| `source_engine` | `str` | `tesseract-<version>` |
| `bbox_left` | `int` | OCR line 左上 x |
| `bbox_top` | `int` | OCR line 左上 y |
| `bbox_width` | `int` | OCR line 寬 |
| `bbox_height` | `int` | OCR line 高 |

## 3. SkippedSegment

`SkippedSegment.type` 新增 `ocr_empty`。

語意：
- `ocr_empty`：成功 decode/OCR，但無任何可辨識文字

## 4. Vector chunk metadata

image-origin chunk metadata 仍走既有 `VectorChunk.metadata`，但新增：

| 欄位 | 說明 |
|---|---|
| `source_format` | `png` / `jpg` / `jpeg` |
| `ocr_confidence` | 命中 chunk 的 confidence |
| `source_engine` | `tesseract-<version>` |
| `bbox_*` | OCR line 邊界 |

`format` 與 `source_format` 並存：前者維持舊路徑，後者給 query trace / agent 使用。

## 5. Ingest file report

`trace.steps[kind="ingest_summary"].detail.files[]` 的 file report 新增：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `source_format` | `string|null` | 所屬來源格式 |
| `ocr_chunks` | `integer|null` | image 檔輸出的 OCR segment 數 |
| `ocr_confidence_min` | `number|null` | 最低 line confidence |
| `ocr_confidence_max` | `number|null` | 最高 line confidence |
| `ocr_engine` | `string|null` | `tesseract-<version>` |

## 6. Parser fingerprint

image parser fingerprint 固定格式：

```text
{format}:v{pillow_version}:{preprocess_signature}:{tesseract_version+langs}:off
```

例：

```text
png:v12.2.0:exif_transpose+grayscale+autocontrast:tesseract-5.5.2+eng+chi_tra:off
```

## 7. Environment contract

| Env | 預設 | 說明 |
|---|---|---|
| `HKS_IMAGE_TIMEOUT_SEC` | `30` | 單檔 image ingest timeout |
| `HKS_IMAGE_MAX_FILE_MB` | `20` | 單檔 image 原始檔上限 |
| `HKS_IMAGE_MAX_PIXELS` | `100000000` | decode 後像素總量上限 |
| `HKS_OCR_LANGS` | `eng+chi_tra` | tesseract language set |
