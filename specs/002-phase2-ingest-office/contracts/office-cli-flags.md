# Contract: Office-related CLI Flags & Environment

**Feature**: 002-phase2-ingest-office
**Status**: Stable（變更預設值屬 MINOR；新增 flag 屬 MINOR；改變既有 flag 語意屬 MAJOR）

## 1. `--pptx-notes`

**Scope**: `ks ingest` 子指令

**語法**：

```bash
ks ingest <path> [--pptx-notes include|exclude]
```

**預設**：`include`

**語意**：
- `include`：pptx parser 抽取每張 slide 的 speaker notes，作為 `Segment(kind="notes")` 併入文字流；每檔 `IngestFileReport.pptx_notes = "included"`。
- `exclude`：pptx parser 不讀取 speaker notes，不建立對應 segment；`IngestFileReport.pptx_notes = "excluded"`。
- 對非 pptx 檔：flag 無作用，`IngestFileReport.pptx_notes = null`。

**對 re-ingest 判定的影響**：
- `--pptx-notes` 值 納入 `parser_fingerprint` 的 `flags_digest`：
  - `include` → `flags_digest = ""`（不改變 fingerprint，與 Phase 1 行為一致）
  - `exclude` → `flags_digest = "notes_exclude"`
- 已 ingest 的 pptx 若 flag 切換值，則在內容 SHA256 不變時仍因 fingerprint 不符而自動觸發 re-ingest（FR-033 / FR-044）。

**對 log.md 的影響**：
- 每檔 pptx ingest 事件於既有 event header 下追加 `- pptx_notes: included` 或 `- pptx_notes: excluded` bullet。
- 非 pptx 事件不出現此欄位。

**Exit code**：flag 值不合法（非 `include` / `exclude`）→ `EXIT_USAGE=2`。

## 2. 環境變數

| 變數 | 預設 | 範圍 | 作用 |
|---|---|---|---|
| `HKS_OFFICE_TIMEOUT_SEC` | `60` | 5–600 | 每檔 Office parser 處理時限。超過 → 該檔 `FAILED / DATAERR=65`、整批 ingest 不中斷。 |
| `HKS_OFFICE_MAX_FILE_MB` | `200` | 1–2048 | 每檔 Office 大小上限。超過 → 該檔 `FAILED / DATAERR=65`、不進入 parse。 |
| `HKS_MAX_FILE_MB` | `200` | 1–2048 | Phase 1 既有，作用於 txt/md/pdf。Office 格式**不**受此變數影響。 |

**邊界行為**：
- 變數值不在合法範圍 → CLI 啟動即以 `EXIT_USAGE=2` 失敗，錯誤訊息指出變數名與可接受範圍。
- 三個變數互不覆寫。

## 3. 新增的 Exit Code 情境

無新增 exit code 值。下列新情境皆歸入 Phase 1 已定義的 code。**本表僅列 `65 DATAERR` 與 `2 USAGE` 新情境；skip 類情境（空檔、副檔名 unsupported、已 ingest 未變更）沿用 Phase 1 `0 OK`，不重列。**

| 情境 | Exit Code | stderr 首行範例 |
|---|---|---|
| 加密 pptx / docx / xlsx | `65 DATAERR` | `[ks:ingest] error: file encrypted: raw_sources/secret.pptx` |
| 位元組損壞 / parser 開啟失敗 | `65 DATAERR` | `[ks:ingest] error: corrupt file: raw_sources/broken.xlsx` |
| 單檔超時（> 60s soft default） | `65 DATAERR` | `[ks:ingest] error: timeout after 60s: raw_sources/huge.pptx` |
| 單檔過大（> 200MB soft default） | `65 DATAERR` | `[ks:ingest] error: file too large (300MB): raw_sources/huge.xlsx` |
| `--pptx-notes` 值錯誤 | `2 USAGE` | `[ks:ingest] usage: invalid value for --pptx-notes: expected 'include' or 'exclude'` |
| `HKS_OFFICE_TIMEOUT_SEC` / `HKS_OFFICE_MAX_FILE_MB` 不合法 | `2 USAGE` | `[ks:ingest] usage: HKS_OFFICE_TIMEOUT_SEC must be in [5, 600], got 9999` |

**批次語意（沿用 Phase 1 FR-003）**：
- 批次中有任一檔走 `DATAERR` → 整個 `ks ingest` 結束 exit code 為 `65`。
- 僅 skip / unsupported / success 的批次 → exit code `0`。

**Runtime boundary**：
- `msoffcrypto-tool` 僅用於 fixture 生成，不屬 runtime 依賴。
- runtime 對加密 / 損壞的判定應來自 parser / zip container / OOXML package 檢查，而不是直接依賴 dev-only 套件的 exception type。

## 4. `--prune`（Phase 1 既有，補充說明）

`--prune` 在 Phase 2 階段一不變更語意：清除 manifest 中 raw_sources 已不存在檔案的 derived artifacts。Office 格式納入相同邏輯。
