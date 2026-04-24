# Contract: Office Placeholder Prefix

**Feature**: 002-phase2-ingest-office
**Status**: Stable（跨三個 parser 共用；變更字面屬 MINOR 擴充、移除屬 MAJOR）

## 用途

Office parser 遇到無法轉為純文字的段落（嵌入圖片、OLE object、SmartArt、macros、影片、音訊、Chart、PivotTable）時，以固定前綴佔位符保留於文字流中對應位置，避免上下文被斷開；同時於 `SkippedSegment` 計數中記錄，供 `wiki/log.md` 與 ingest stdout JSON 輸出。

Phase 3 OCR / VLM 實作時，以 regex `\[<type>: [^\]]*\]` 就地替換佔位符字面，不需重 ingest 整份檔。

## 八種固定佔位符

所有佔位符為 **純 ASCII**、字面固定、大小寫敏感。前綴 `[<type>: ` 七字必為 literal，`<alt>` / `<type>` 欄位可為空字串。

| `SkippedSegmentType` | 佔位字面 | 說明 |
|---|---|---|
| `image` | `[image: <alt-text 或空>]` | 文件內嵌圖片；`<alt-text>` 取 docx `w:drawing/wp:docPr/@descr` 或 pptx `Picture.shape.name`，不存在時留空 |
| `embedded_object` | `[embedded object: <type>]` | OLE object；`<type>` 為 MIME 或原始 ProgID（如 `Excel.Sheet.12`） |
| `smartart` | `[smartart: <summary 或空>]` | SmartArt；`<summary>` 可取 SmartArt 第一個節點標題，不存在時留空 |
| `macros` | `[macros: skipped]` | VBA macros；不執行、不展開內容 |
| `video` | `[video: skipped]` | pptx 嵌入影片 |
| `audio` | `[audio: skipped]` | pptx 嵌入音訊 |
| `chart` | `[chart: skipped]` | xlsx / pptx Chart 物件 |
| `pivot` | `[pivot: skipped]` | xlsx PivotTable |

## 驗證規則

- parser 輸出的 `Segment(kind="placeholder")` 的 `text` 必為八種字面之一（尾部 `<alt>` / `<type>` 欄可為任意 ASCII，但不得含 `]`）。
- `SkippedSegment.type` 必為上表 `SkippedSegmentType` 清單之一；`count` ≥ 1。
- `empty_slide` 為獨立 `SkippedSegmentType`，但 **不** 有對應的佔位字面（因為整張 slide 無內容，不需要插入文字）。

## 契約測試

`tests/contract/test_placeholder_prefix.py` 須涵蓋：

1. 八種 type 的 regex 匹配：`\[(image|embedded object|smartart|macros|video|audio|chart|pivot): [^\]]*\]`。
2. Parser 產出的每個 placeholder segment 字面 round-trip 驗證（解析後回填的 type 與實際一致）。
3. 負面測試：
   - 前綴大寫（`[Image: ...]`）→ 應視為一般文字，不計入 `skipped_segments`。
   - 缺冒號空白（`[image:x]`）→ 視為一般文字。
   - 非 ASCII 類型名（`[圖片: ...]`）→ 視為一般文字；parser 不得以此格式產生。
