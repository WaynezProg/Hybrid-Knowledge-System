# Feature Specification: PageIndex Integration & System-wide Improvements

**Feature Branch**: `013-pageindex-integration`
**Created**: 2026-05-19
**Status**: Draft
**Input**: Integrate VectifyAI/PageIndex hierarchical tree concept into HKS wiki layer; fix document structure loss; improve routing, graph extraction, and test coverage.

## Clarifications

- Q: PageIndex tree 是否取代 wiki page？ -> A: 不取代。Tree 是新的 artifact 類型，跟 wiki page 共存。Wiki page 保留 summary/body；tree 提供 hierarchical navigation。
- Q: Rule-based tree 是否需要 LLM？ -> A: 不需要。Rule-based tree 在 `ks ingest` 時從 parser 結構資訊建構，零 LLM 成本。LLM enrichment 是可選的獨立步驟。
- Q: PageIndex 的 LLM agent retrieval 是否搬進 `ks query`？ -> A: 不搬。Query 維持零 LLM 成本。Tree 只在 ingest/enrich 時用 LLM，query 時用 tree 的 title/summary 做 routing 判斷。
- Q: 是否修改 authoritative wiki/graph/vector？ -> A: Phase 1 不改 wiki/graph 內容。只新增 `page_trees/` artifact、擴充 chunk metadata、增強 PDF parser segments。Phase 2-3 改 routing 和 graph extraction 邏輯但不改已儲存的資料結構。
- Q: 已 ingest 的文件會怎樣？ -> A: PDF 的 `parser_fingerprint` 會因 parser 改動而改變，觸發 re-ingest（正確行為）。其他格式 fingerprint 不變，不會觸發 re-ingest，但也不會有 tree（需手動 re-ingest 或等 watch 觸發）。
- Q: tree 檔名跟 wiki page slug 的對應關係？ -> A: tree 檔名使用 source 的 relpath 經 `slug_base()` 轉換，跟 wiki page slug 可能不同（wiki slug 基於 title）。manifest 的 `DerivedArtifacts.page_tree` 記錄 tree slug，是唯一的對應來源。
- Q: `ks pageindex enrich` 對已經是 `build_method="llm"` 的 tree 怎麼處理？ -> A: 預設 skip，除非指定 `--force` 重新 enrich。避免重複消耗 LLM token。

## Phasing

本 spec 涵蓋四個 phase，每個 phase 可獨立交付：

| Phase | 範圍 | 依賴 |
|-------|------|------|
| 1 | PageIndex tree + 文件結構修復 | 無 |
| 2 | Routing 改善 | Phase 1 |
| 3 | Graph extraction 強化 | Phase 1 |
| 4 | 測試補齊 | 隨每個 phase 增量做 |

---

# Phase 1: PageIndex Tree + Document Structure

## Data Model

### TreeNode

```python
@dataclass(frozen=True, slots=True)
class TreeNode:
    node_id: str              # dot-separated hierarchy: "n1", "n1.2", "n1.2.3"
    title: str                # "Executive Summary", "Slide 3", "Sheet: Revenue"
    level: int                # 1-based depth in tree
    start_offset: int         # character offset in normalized text
    end_offset: int           # character offset in normalized text
    children: list[TreeNode]  # recursive
    summary: str = ""         # empty for rule-based, LLM fills later
    metadata: dict = {}       # format-specific: page_number, slide_index, sheet_name
```

### PageTree

```python
@dataclass(frozen=True, slots=True)
class PageTree:
    source_relpath: str       # "report.pdf"
    source_format: str        # "pdf", "docx", "pptx", "xlsx", "md", "txt"
    doc_title: str            # from parser's extracted title
    root_nodes: list[TreeNode]
    build_method: str         # "rule" or "llm"
    built_at: str             # ISO timestamp
    total_nodes: int          # flat count for quick stats
    source_sha256: str        # idempotency check
```

### Design Decisions

- **Offset 用 char offset**：統一跨格式（txt/md 沒有 page 概念）；page_number 放 metadata
- **node_id 用 dot-separated hierarchy**（`n1.2.3`）：從 id 可看出層級，不需 traverse
- **frozen dataclass**：tree 建好後不可變，LLM enrich 產生新 tree
- **children nested in node**：跟 PageIndex 原版一致，tree traversal 自然

### JSON Schema

```json
{
  "source_relpath": "report.pdf",
  "source_format": "pdf",
  "doc_title": "2025 Q1 Report",
  "build_method": "rule",
  "built_at": "2026-05-19T01:30:00Z",
  "total_nodes": 7,
  "source_sha256": "a1b2c3...",
  "root_nodes": [
    {
      "node_id": "n1",
      "title": "Executive Summary",
      "level": 1,
      "start_offset": 0,
      "end_offset": 1200,
      "summary": "",
      "metadata": {"page_start": 1, "page_end": 3},
      "children": []
    },
    {
      "node_id": "n2",
      "title": "Financial Results",
      "level": 1,
      "start_offset": 1200,
      "end_offset": 5800,
      "summary": "",
      "metadata": {"page_start": 4, "page_end": 12},
      "children": [
        {
          "node_id": "n2.1",
          "title": "Revenue Breakdown",
          "level": 2,
          "start_offset": 1200,
          "end_offset": 3400,
          "summary": "",
          "metadata": {"page_start": 4, "page_end": 7},
          "children": []
        }
      ]
    }
  ]
}
```

## Module Structure

```
src/hks/page_tree/
├── __init__.py
├── model.py      # PageTree, TreeNode dataclasses + JSON serialization
├── build.py      # rule-based builders (per format) + format dispatch
├── enrich.py     # LLM enrichment logic
└── store.py      # read/write/delete $KS_ROOT/page_trees/{slug}.json
```

## Rule-based Builders

Builder 簽名統一：`build_tree(parsed: ParsedDocument, normalized_text: str) -> list[TreeNode]`

### Per-format Strategy

**MD**：解析 `#` heading 層級，巢狀依 level。無 heading → 單一 root node。

**TXT**：無結構 → 單一 root node 包住整份文件。

**DOCX**：從 segments 的 `heading` kind + `level` metadata 建 tree。非 heading segments 歸屬最近上層 heading。

**PPTX**：每張 slide（`slide_header` segment）為 level-1 node。Slide 內 heading 為 level-2 child。Notes 記錄在 parent slide metadata。

**XLSX**：每個 sheet（`sheet_header` segment）為 level-1 leaf node。

**PDF**：見下方 PDF Parser Enhancement。

**Image (png/jpg/jpeg)**：OCR 文字無結構 → 單一 root node。

### Offset Alignment

共用 helper `align_offsets(title, normalized_text, search_start) -> (int, int)` 在 normalized_text 中定位 heading/section 位置。找不到時 fallback 用 segment token 累計位置估算。

### Degenerate Tree

無結構格式統一產出 `total_nodes: 1` 的單一 root node。Downstream 可據此判斷是否值得用 tree 資訊。

## PDF Parser Enhancement

目前 `src/hks/ingest/parsers/pdf.py` 只回傳 raw text，不產出 segments。改為也產出 segments，跟 DOCX/PPTX/XLSX 一致。

### Extraction Logic（三階段 fallback）

**Phase A — TOC Bookmark**：`doc.get_toc()` 回傳 `[(level, title, page_num), ...]`。有 TOC 時直接建 heading + paragraph segments，每個 segment 帶 `page_number` metadata。

**Phase B — Font Size Heuristic**：無 TOC 時，用 `page.get_text("dict")` 取每個 span 的 font size。`size > median × 1.5` → level-1 heading；`median × 1.3 < size ≤ median × 1.5` → level-2。過濾純數字、單字元、頁首頁尾重複文字。

**Phase C — Fallback**：兩者都沒有 → 不產出 segments，退化為現行行為。

### Dependencies

PyMuPDF (`fitz`) 已在使用中。`get_toc()` 和 `get_text("dict")` 是同一套件 API，不需新依賴。

### Compatibility

- 有 segments 的 PDF → normalizer 走 `segment_aware_chunks()`
- 無 segments → 走 `normalizer.chunk()`（不變）
- `parser_fingerprint` 改變 → 已 ingest 的 PDF 觸發 re-ingest

## Pipeline Integration

### Ingest Flow Change

在 `pipeline.py` 的 `ingest()` 中，tree 建構插在 parse 完成後、wiki/graph/vector 寫入前：

```python
extracted = extractor.extract(...)
page_tree = build_page_tree(parsed, normalized_text, source_format)  # new
tree_store.save(relpath, page_tree)                                   # new
shutil.copy2(file_path, raw_target)
page = wiki_store.write_page(...)
graph_artifacts = extract_document_graph(...)
graph_store.replace_document(...)
vector_chunks = _attach_tree_node_ids(vector_chunks, page_tree, chunks)  # new
vector_ids = vector_store.add_chunks(vector_chunks)
```

### Chunk Metadata Enrichment

`_attach_tree_node_ids()` 對每個 chunk 查找其 text 落在哪個 tree node 的 `[start_offset, end_offset)` 範圍，加兩個欄位：

```python
{"tree_node_id": "n2.1", "tree_node_title": "Revenue Breakdown"}
```

跨 node boundary 的 chunk 歸屬到 `start_offset` 所在的 node。

### Storage Layout

```
$KS_ROOT/
├── page_trees/          # new
│   ├── report-pdf.json
│   └── slides-pptx.json
├── wiki/
├── graph/
├── vector/
└── manifest.json
```

Tree 檔名用 `WikiStore.slug_base()` 同規則，保證 filesystem safe。

### Manifest Extension

`DerivedArtifacts` 新增欄位：

```python
page_tree: str | None = None  # tree JSON filename without .json
```

### Rollback

失敗時刪除 `page_trees/{slug}.json`，加在現有 rollback block 裡。

### Idempotency

Tree 的 `source_sha256` + `build_method` 構成 idempotency key。SHA256 不變 + build_method 不變 → skip rebuild。

## LLM Tree Enrichment

### CLI

```bash
ks pageindex enrich [--source-relpath <relpath>] --mode preview|store [--provider fake|openai]
```

- 不指定 `--source-relpath` → 對所有 rule-based tree 做 enrichment
- `preview` → stdout 輸出，不改檔
- `store` → 寫回 `page_trees/{slug}.json`，`build_method` 改為 `"llm"`
- `--provider fake` → deterministic fake LLM

### LLM Tasks

**補 summary**：每個 node 用 LLM 生成 1-2 句 summary，基於 node 對應的原文範圍。

**結構修正（僅退化 tree）**：`total_nodes == 1` 時，LLM 嘗試從文字內容識別段落結構，重新建 tree。`total_nodes > 1` 時不做結構修正，只補 summary。

### Relationship to Other Enrichment Commands

```
ks ingest              → rule-based tree (build_method="rule")
ks llm classify        → llm/extractions/
ks pageindex enrich    → enriched tree (build_method="llm")
ks wiki synthesize     → richer wiki pages
ks graphify build      → derived graph communities
```

`pageindex enrich` 不依賴 `llm classify`，也不被 `wiki synthesize` 依賴。三者可獨立執行、任意順序。

## Lint Rules

| Rule | Severity | Description |
|------|----------|-------------|
| `tree_missing` | warning | manifest 有 `page_tree` 但檔案不存在 |
| `tree_orphan` | warning | `page_trees/` 有檔案但 manifest 無對應 entry |
| `tree_offset_mismatch` | info | tree node 的 `end_offset > len(normalized_text)` |
| `tree_node_chunk_gap` | info | chunk offset 不落在任何 tree node 範圍內 |

## MCP + HTTP Adapter

| Interface | Endpoint / Tool | Description |
|-----------|----------------|-------------|
| CLI | `ks pageindex show <relpath>` | 顯示 source 的 tree |
| CLI | `ks pageindex enrich --mode preview\|store` | LLM enrichment |
| MCP | `pageindex_show`, `pageindex_enrich` | 對應 CLI |
| HTTP | `GET /pageindex/{relpath}`, `POST /pageindex/enrich` | 對應 CLI |

---

# Phase 2: Routing Improvements

## Wiki Search Upgrade

現行 `WikiStore.search()` 是 O(n) keyword scoring。改為兩階段：

**Stage 1 — Tree summary scan**：讀所有 `page_trees/*.json`，對 tree node 的 `title` + `summary` 做 keyword matching。回傳 `(source_relpath, node_id, score)` 列表。

**Stage 2 — Focused wiki lookup**：只對 Stage 1 匹配到的 source 對應的 wiki pages 做完整 scoring。從 O(n × body_length) 降到 O(k × body_length)，k << n。

## Multi-layer Fusion

Route decision 擴充為 primary + secondary：

```python
@dataclass
class RouteDecision:
    primary: Route          # "wiki" | "graph" | "vector"
    secondary: Route | None # graph miss 可先試 wiki
    confidence: float
```

Routing rules YAML 擴充 `secondary` 欄位。Query 執行順序：primary → miss → secondary → miss → vector（ultimate fallback）。

## Vector Hit Section Context

Vector 回傳的 chunk 帶 `tree_node_id` + `tree_node_title`。Query response 新增：

```json
{
  "sources": [{
    "source_relpath": "report.pdf",
    "section_path": "Financial Results > Revenue Breakdown",
    "page_range": "pp. 4-7"
  }]
}
```

`section_path` 由 `tree_node_id` 往上 traverse 到 root 拼出。

---

# Phase 3: Graph Extraction Enhancement

## Tree-aware Extraction

`extract_document_graph()` 新增 `page_tree: PageTree | None` 參數。有 tree 時：

- 每個 tree node 自動成為 `belongs_to` 關係的 entity（section 屬於 document）
- Regex extraction 在每個 section 文字範圍內獨立執行
- `evidence` 欄位加上 section context（node_id + title）
- Entity dedup 記錄出現位置（哪些 sections）

## New Relation Types

擴充 3 種 relation type（從 5 → 8）：

| Type | Example Patterns |
|------|-----------------|
| `causes` | "X 導致 Y", "X causes Y", "X 造成 Y" |
| `contradicts` | "X 但 Y", "X however Y", "與 X 矛盾" |
| `succeeds` | "X 之後 Y", "X followed by Y", "接續 X" |

## Entity Type Contextual Heuristic

補充 rule-based heuristic（不引入 LLM）：

- Entity 出現在 tree node title → 更可能是 Project / Document
- Entity 是 `causes`/`impacts` 的 subject → 更可能是 Event
- Entity 被多個其他 entity `depends_on` → 更可能是 System / Concept

---

# Phase 4: Test Coverage

## New Module Tests

| Target | Type | Coverage |
|--------|------|----------|
| `page_tree/model.py` | Unit | serialize/deserialize round-trip, node_id consistency |
| `page_tree/build.py` per format | Unit | fixture-based tree structure validation |
| PDF heading heuristic | Unit | TOC / no-TOC / degenerate cases |
| `page_tree/enrich.py` | Unit | fake provider summary, degenerate tree restructure |
| `page_tree/store.py` | Unit | save/load/delete round-trip |
| Pipeline + tree integration | Integration | tree exists after ingest, chunk metadata has `tree_node_id` |
| `ks pageindex enrich` CLI | Integration | preview no-op, store writes file |
| Routing multi-layer fusion | Integration | primary → secondary → ultimate fallback chain |

## Existing Gap Coverage

| Target | Type | Description |
|--------|------|-------------|
| `commands/` module | Unit | CLI argument parsing + dispatch |
| `graph/extract.py` edge cases | Unit | regex pattern boundaries, comma-separated targets |
| PDF segment extraction | Unit | TOC parsing, font size heuristic, page number tracking |

## Fixture Strategy

- 3 small PDF fixtures: with TOC, no TOC but font-size headings, plain text
- Reuse existing `tests/fixtures/valid/` for txt/md/docx/pptx/xlsx
- Fake LLM provider for CI (no API key needed)
