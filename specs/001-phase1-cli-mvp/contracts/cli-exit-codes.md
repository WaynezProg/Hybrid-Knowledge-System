# CLI Exit Code Contract (Phase 1)

**Scope**: `ks ingest`, `ks query`, `ks lint`
**Basis**: 憲法 [§II Stable Output Contract — CLI Exit Codes 附屬契約](../../.specify/memory/constitution.md)（BSD `sysexits.h` 子集）
**Source of truth**: `src/hks/errors.py` 的 `ExitCode` IntEnum

Agent 與 shell script 依 exit code 分支；本表為對外介面的一部分，任何新增 / 變更 **MUST** 走憲法修訂流程。

---

## 總表

| Code | Name | 適用指令 | 情境 | stderr 是否輸出 | stdout JSON 是否仍吐 |
|---|---|---|---|---|---|
| `0` | OK | all | 指令執行成功；含 query 有效命中與 query 無命中但流程正常、lint stub、ingest 成功（部分跳過 / 部分成功視同成功） | 否 | 是 |
| `1` | GENERAL | all | 未分類執行錯誤（磁碟 I/O 失敗、lock 取得失敗、log 寫入失敗等） | 是（錯誤訊息 + traceback 可選） | SHOULD 吐錯誤 JSON |
| `2` | USAGE | all | 指令參數或 flag 錯誤（typer 自動觸發） | 是（typer usage 說明） | 否 |
| `65` | DATAERR | `ks ingest` | 來源解析失敗（壞 PDF、編碼錯誤、超過檔案大小上限、不是正常檔） | 是（哪一檔失敗 + 原因） | SHOULD 吐含 `failures[]` 的 ingest 摘要 JSON |
| `66` | NOINPUT | `ks query`, `ks ingest --prune` | 指令要求的資源不存在（query 前 `/ks/` 未初始化、ingest 目標路徑不存在） | 是 | SHOULD 吐錯誤 JSON |

---

## 指令逐項說明

### `ks ingest <path>`

| 情境 | Exit code | 備註 |
|---|---|---|
| 目錄全部檔案成功 ingest 或 skip | `0` | 摘要 JSON 輸出成功 / 跳過件數 |
| 部分檔失敗（壞 PDF、超大），其餘成功 | `65` | `failures[]` 明列失敗清單；已成功者不 rollback |
| 目標路徑不存在 | `66` | stderr 附提示「path not found: ...」|
| 其他參數錯誤（例 `--unknown-flag`） | `2` | typer 處理 |
| `/ks/.lock` 已存在（並發） | `1` | stderr 指示如何 release lock |
| 磁碟寫入失敗、manifest 讀寫失敗 | `1` | stderr 附 exception summary |

### `ks query "<q>"`

| 情境 | Exit code | 備註 |
|---|---|---|
| 有命中（wiki 或 vector 或 merge） | `0` | JSON schema 完整；`source` 非空 |
| 無命中（wiki + vector 皆空） | `0` | `answer="未能於現有知識中找到答案"`、`source=[]`、`confidence=0.0`；**不返非零** |
| `/ks/` 未曾 ingest（無 manifest.json） | `66` | stderr 附「請先執行 ks ingest」 |
| `config/routing_rules.yaml` 遺失或格式錯 | `1` | stderr 明示 yaml 解析位置 |
| 參數錯誤 | `2` | typer 處理 |
| Embedding model 載入失敗（首次無網路） | `1` | stderr 指示可設 `HKS_EMBEDDING_MODEL` |

### `ks lint`

| 情境 | Exit code | 備註 |
|---|---|---|
| 任何 `/ks/` 狀態 | `0` | 固定吐 stub JSON；不存取 `/ks/` 也不驗證 |
| 參數錯誤 | `2` | typer 處理 |

---

## Stderr 訊息格式

- **人類可讀**：zh-TW 為主、英文可混用（技術術語）。
- **結構**：首行為 `[ks:<command>] <level>: <summary>`，後續可接多行細節。
- **level**：`error`（對應 exit 1/65/66）或 `usage`（exit 2）。
- **不含**彩色 escape codes（避免 pipe 下髒字元）；將來以 `--no-color` / `NO_COLOR` env 控制。

範例:

```
[ks:ingest] error: 無法解析 PDF ./docs/broken.pdf
  原因: pypdf.errors.PdfReadError: EOF marker not found
  已完成: 9 / 10；失敗 1 件
```

```
[ks:query] error: /ks/ 尚未初始化
  請先執行：ks ingest <path>
```

---

## 錯誤情境下的 stdout JSON

在 `1` / `65` / `66` 時，若可行，stdout **SHOULD** 仍輸出符合 [`query-response.schema.json`](./query-response.schema.json) 的 JSON（`answer` 填錯誤說明、`source=[]`、`confidence=0.0`、`trace.steps` 含 `kind="error"` 步驟）。這降低 agent 的解析特例，使 agent 能以「解析 JSON + 讀 exit code」兩步驟處理所有情境。

`2` USAGE 不吐 JSON，因 typer 的 usage 流程由框架掌管，強塞 JSON 會干擾 `--help`。

範例（`ks query` 於 `/ks/` 未初始化時）:

```json
{
  "answer": "/ks/ 尚未初始化，請先執行 ks ingest <path>",
  "source": [],
  "confidence": 0.0,
  "trace": {
    "route": "wiki",
    "steps": [
      { "kind": "error", "detail": { "code": "NOINPUT", "exit_code": 66, "hint": "run `ks ingest`" } }
    ]
  }
}
```

---

## 測試策略

- `tests/contract/test_exit_codes.py`：以 subprocess 驅動 CLI，涵蓋本表所有「情境 → exit code」組合。
- `tests/contract/test_json_schema.py`：`1 / 65 / 66` 情境下仍驗證 stdout（若有輸出）符合 schema。
- `2` USAGE 情境透過 typer 測試（`CliRunner`）驗證 help / error 文案。
