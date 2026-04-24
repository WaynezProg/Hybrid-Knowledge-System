# Phase 1 — Data Model: Office Ingest Extension

**Feature**: 002-phase2-ingest-office
**Scope**: 定義新增與擴充的資料型別，供 tasks.md 與實作對齊。所有欄位型別以 Python `dataclass` 風格表達；持久化格式（JSON in manifest、YAML in routing rules、Markdown in wiki）於各小節分別標示。

## 1. 擴充：`ParsedDocument`

Phase 1 現況（見 `src/hks/ingest/models.py`）：

```python
@dataclass(slots=True)
class ParsedDocument:
    title: str
    body: str
    format: SourceFormat
```

**Phase 2 階段一擴充**：

```python
@dataclass(slots=True)
class ParsedDocument:
    title: str
    body: str                                    # normalized 後的全文（含佔位符）
    format: SourceFormat
    segments: list[Segment] = field(default_factory=list)
    skipped_segments: list[SkippedSegment] = field(default_factory=list)
    parser_fingerprint: str = ""                 # 由 pipeline 寫入，parser 不負責
```

**欄位語意**：
- `body`：為 backward compat 保留；Phase 1 parser（txt / md / pdf）仍只使用此欄位。
- `segments`：有序、可 chunk 的細粒度單位。Office parser 的主要輸出路徑。當 `segments` 非空時，`body` 由 `segments` 串接產生（pipeline 層處理，parser 不重複填）。
- `skipped_segments`：ingest 時跳過的非文字元素（記錄 type + count + 位置）。
- `parser_fingerprint`：識別 parser 版本 + 影響結果的 flag 組合，供 idempotency 比對。

**向後相容**：Phase 1 三個 parser 不改動；pipeline 在進入 `extractor` 前會檢查 `segments` 是否為空，若空則 fallback 到既有 body-based chunk 邏輯。

## 2. 新增：`Segment`

```python
SegmentKind = Literal[
    "paragraph",      # docx 段落 / pptx 本文
    "heading",        # docx 標題 / pptx slide title
    "list_item",      # docx bullet / numbered
    "table_row",      # xlsx row / docx table row / pptx table row
    "sheet_header",   # xlsx sheet 的 H2 子標題（"## <sheet name>"）
    "slide_header",   # pptx slide 的 H2 子標題（"## Slide <n>"）
    "notes",          # pptx speaker notes
    "placeholder",    # 嵌入圖片 / object / macros 等佔位符
]

@dataclass(slots=True)
class Segment:
    kind: SegmentKind
    text: str                                    # 段落純文字（可含佔位符字面）
    metadata: dict[str, Any] = field(default_factory=dict)
```

**`metadata` 依 `kind` 不同鍵**（permitted keys，非必填）：

| `kind` | 鍵 | 範例值 |
|---|---|---|
| `heading` | `level` | `1` / `2` / `3`（docx heading 層級） |
| `table_row` | `sheet_name` / `row_index`（1-based，與 `slide_index` 基底一致）/ `header_row` | `"Sheet1"` / `3` / `["id","name"]` |
| `sheet_header` | `sheet_name` | `"Sheet1"` |
| `slide_header` | `slide_index` | `5`（1-based） |
| `notes` | `slide_index` | `5` |
| `placeholder` | `placeholder_type` | `"image"` / `"embedded object"` / `"macros"` 等八種之一 |

**Chunk 規則**：
- chunk 邊界優先落在 `heading` 前、`sheet_header` / `slide_header` 前。
- 長度超過 chunk 上限（512 token）時，以 `paragraph` / `list_item` / `table_row` 為最小切分粒度，不在 placeholder 中間切。

## 3. 新增：`SkippedSegment`

```python
SkippedSegmentType = Literal[
    "image",
    "embedded_object",
    "smartart",
    "macros",
    "video",
    "audio",
    "chart",
    "pivot",
    "empty_slide",
]

@dataclass(slots=True)
class SkippedSegment:
    type: SkippedSegmentType
    count: int = 1
    location: str | None = None                  # 例："sheet=Sheet1,row=3" / "slide=5"
```

**序列化為 log.md**（Phase 1 `wiki/log.md` 事件的額外 bullet 明細）：

```markdown
## 2026-05-01 08:30 | ingest | created
- target: raw_sources/meeting-notes.pptx
- skipped_segments: image:3,embedded_object:1
```

`skipped_segments` 值以逗號分隔的 `type:count` 清單表示；解析時順序不重要；`location` 僅於更細節的 debug log 用，不進入 `log.md`。

**序列化為 ingest stdout JSON**（置於 `trace.steps[kind="ingest_summary"].detail.files[]`；見 `contracts/ingest-summary-detail.schema.json`）：

```json
{
  "path": "project/deck.pptx",
  "status": "created",
  "skipped_segments": [
    { "type": "image", "count": 4 },
    { "type": "macros", "count": 1 }
  ],
  "pptx_notes": "included"
}
```

## 4. 擴充：`ManifestEntry`

Phase 1 現況（見 `src/hks/core/manifest.py`）：

```python
@dataclass(slots=True)
class ManifestEntry:
    relpath: str
    sha256: str
    format: SourceFormat
    size_bytes: int
    ingested_at: str
    derived: DerivedArtifacts
```

**Phase 2 階段一擴充**：

```python
@dataclass(slots=True)
class ManifestEntry:
    relpath: str
    sha256: str
    format: SourceFormat
    size_bytes: int
    ingested_at: str
    derived: DerivedArtifacts
    parser_fingerprint: str = "*"                # 新欄位；舊 entry 以 "*" 視為 wildcard
```

**`SourceFormat` Literal 擴充**（於 `src/hks/core/manifest.py`）：

```python
SourceFormat = Literal["txt", "md", "pdf", "docx", "xlsx", "pptx"]
```

**JSON schema（manifest.json 片段）**：

```json
{
  "relpath": "specs/s1.xlsx",
  "sha256": "a3f…",
  "format": "xlsx",
  "size_bytes": 48201,
  "ingested_at": "2026-05-01T08:30:00Z",
  "derived": {
    "wiki_pages": ["s1"],
    "vector_ids": ["vec-s1-0", "vec-s1-1", "vec-s1-2"]
  },
  "parser_fingerprint": "xlsx:v3.1.2:"
}
```

**`parser_fingerprint` 字串格式**：`{format}:v{library_version}:{flags_digest}`
- `library_version`：來自 `importlib.metadata.version("openpyxl")` 等。
- `flags_digest`：影響解析結果的 flag 的穩定序列化（例：pptx `notes=exclude` → `flags_digest = "notes_exclude"`；預設 include → 空字串）。

**Re-ingest 判定流程**（pipeline.py）：

```
for each source file:
    current_sha = sha256(file)
    current_fp  = compute_parser_fingerprint(format, flags)
    entry = manifest.get(path)
    if entry and entry.sha256 == current_sha and entry.parser_fingerprint in (current_fp, "*"):
        skip
    elif entry:
        update (rollback-safe)
    else:
        create
```

`"*"` 為舊 Phase 1 manifest 寬鬆繼承值；第一次被 re-ingest 時 pipeline 會寫入具體 fingerprint 取代。

## 5. 新增：`IngestFileReport`（ingest summary 子記錄）

Phase 1 現況：`IngestSummary` 含 `created`/`updated`/`skipped`/`failures`/`pruned` 五個清單，元素為 `str` 或 `IngestIssue`；`src/hks/commands/ingest.py` 會把它包進既有 `QueryResponse` 的 `trace.steps[kind="ingest_summary"].detail`。

**Phase 2 階段一擴充**：將「每檔狀態 + 附屬欄位」統一為 dataclass：

```python
FileStatus = Literal["created", "updated", "skipped", "failed", "unsupported"]

@dataclass(slots=True)
class IngestFileReport:
    path: str
    status: FileStatus
    reason: str | None = None                    # skipped / failed / unsupported 時填
    skipped_segments: list[SkippedSegment] = field(default_factory=list)
    pptx_notes: Literal["included", "excluded"] | None = None  # 僅 pptx 時填

@dataclass(slots=True)
class IngestSummary:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[IngestIssue] = field(default_factory=list)
    failures: list[IngestIssue] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    files: list[IngestFileReport] = field(default_factory=list)
```

**向後相容策略**：保留既有 `created` / `updated` / `skipped` / `failures` / `pruned` 結構，新增 `files` 為 additive 擴充；top-level stdout 仍為 Phase 1 的 `QueryResponse`，`files` 僅作為 `ingest_summary.detail` 的新增欄位。

## 6. CLI Options 擴充

於 `src/hks/cli.py` 的 `ingest` subcommand 新增：

```python
@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(...)],
    prune: Annotated[bool, typer.Option("--prune")] = False,
    pptx_notes: Annotated[
        Literal["include", "exclude"],
        typer.Option("--pptx-notes", help="pptx speaker notes 是否納入 ingest（預設 include）"),
    ] = "include",
) -> None: ...
```

**對 `parser_fingerprint` 的影響**：
- `--pptx-notes=include` → `flags_digest = ""`（預設、不影響 fingerprint）
- `--pptx-notes=exclude` → `flags_digest = "notes_exclude"`

其他格式（docx / xlsx）目前無 parser-level flag，`flags_digest` 為空字串。

## 7. Environment Variables

| 變數 | 預設 | 範圍 | 對應 FR |
|---|---|---|---|
| `HKS_OFFICE_TIMEOUT_SEC` | `60` | 5–600 | FR-063 |
| `HKS_OFFICE_MAX_FILE_MB` | `200` | 1–2048 | FR-064 |
| `HKS_EMBEDDING_MODEL` | （Phase 1 預設） | — | 沿用 |
| `HKS_MAX_FILE_MB` | `200` | — | Phase 1 既有（對 txt/md/pdf 生效） |

`HKS_OFFICE_MAX_FILE_MB` 與 `HKS_MAX_FILE_MB` 為互不覆寫、分別作用於 Office / 非 Office 格式；兩者皆無設定時皆以 200 為準。

## 8. Log Entry 擴充（`wiki/log.md`）

Phase 1 ingest 事件格式：

```
2026-05-01T08:30:00Z | ingest | created | target=<slug>
```

**Phase 2 階段一擴充**（不新增事件類型，僅加附屬 bullet）：

```
## 2026-05-01 08:30 | ingest | created
- target: raw_sources/meeting-notes.pptx
- skipped_segments: image:3,macros:1
- pptx_notes: included

## 2026-05-01 08:45 | ingest | failed
- target: raw_sources/secret-plan.pptx
- reason: encrypted
```

**解析規則**：
- `## <timestamp> | <event> | <status>` header 與 Phase 1 完全相同。
- `skipped_segments` / `pptx_notes` 僅作為額外 bullet 明細追加。
- 既有只讀 header+bullet 的 parser 不需理解新欄位，仍可忽略未知 key。

**既有 Phase 1 log.md 內容**：零影響；新增附屬欄位不破壞舊行解析。

## 9. Routing Rules 配置

**變動**：無。`config/routing_rules.yaml` 維持 Phase 1 原貌（summary / detail / relation 三條 rule、中英 keyword、`default_route: vector`、`version: 1`）。

**理由**：spec FR-052 明訂 `source` / `trace.route` 不得擴增新值；本 spec 不新增 route，僅新增來源格式。

## 10. 向後相容性摘要

| 面向 | Phase 1 既有 | Phase 2 階段一 變更 | 破壞性? |
|---|---|---|---|
| QueryResponse top-level | `{answer, source, confidence, trace}` | 零變更 | 否 |
| Exit codes | 0/1/2/65/66 | 零變更 | 否 |
| Routing rules | summary/detail/relation 三條 | 零變更 | 否 |
| `/ks/` 目錄結構 | `raw_sources/ wiki/ vector/db/ manifest.json` | 零變更 | 否 |
| `/ks/graph/` | 禁止 | 持續禁止 | 否 |
| ManifestEntry | `relpath/sha256/format/size_bytes/ingested_at/derived` | 新增 `parser_fingerprint` 欄位（舊 entry 以 `"*"` 視為 wildcard） | 否（自動遷移） |
| ingest_summary.detail | 既有 counters | 新增 `files` 陣列 + 每檔 `skipped_segments` / `pptx_notes` | 相容擴充 |
| log.md 事件 | header + bullet 明細 | 可附加 `- skipped_segments:` / `- pptx_notes:` bullet | 否（舊 log 解析可忽略未知 key） |
| CLI flags | `--prune` | 新增 `--pptx-notes` | 否（新增） |

整體對外契約為 **backward compatible MINOR 擴充**；agent / script 不需改動即可繼續解析 Phase 1 行為。
