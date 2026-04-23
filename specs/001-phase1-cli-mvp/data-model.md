# Data Model: HKS Phase 1 MVP

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-23

本文件為 Phase 1 產出。以 Python `dataclasses` 表述；序列化 / 驗證交由 `core/schema.py` + `jsonschema`。識別字與型別使用英文；欄位註解使用 zh-TW（憲法 §語言紀律）。

---

## 總覽

| Entity | 落地位置 | 由誰寫入 | 由誰讀取 |
|---|---|---|---|
| `RawSource` | `/ks/raw_sources/<relpath>` | ingest | ingest（re-ingest 校驗）|
| `ManifestEntry` | `/ks/manifest.json`（單檔） | ingest | ingest, query（存在性校驗）|
| `WikiPage` | `/ks/wiki/pages/<slug>.md` | ingest, writeback | query（wiki route）|
| `WikiIndexEntry` | `/ks/wiki/index.md`（TOC line） | ingest, writeback | query, CLI `--help` 可選列出 |
| `LogEntry` | `/ks/wiki/log.md`（append-only） | ingest, writeback | 人類 / Phase 3 lint |
| `VectorChunk` | `/ks/vector/db/`（chromadb collection） | ingest | query（vector route）|
| `RoutingRule` | `config/routing_rules.yaml` | 人類（dev）| routing |
| `QueryResponse` | stdout（JSON） | cli | agent, 人類 |
| `TraceStep` | 內嵌於 `QueryResponse.trace.steps` | router / pipeline | agent, 除錯 |

---

## 1. `RawSource`

代表被 ingest 的來源檔，immutable。

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Format = Literal["txt", "md", "pdf"]

@dataclass(frozen=True)
class RawSource:
    relpath: Path          # 相對於 ingest root 的路徑；作 manifest key
    sha256: str            # 內容 hash；64 hex 字元
    format: Format
    size_bytes: int
    ingested_at: datetime  # ISO 8601
```

**驗證規則**:
- `sha256` 需通過 `re.fullmatch(r"[0-9a-f]{64}", ...)`。
- `size_bytes` ≤ `HKS_MAX_FILE_MB * 1024 * 1024`（預設 200 MB）。
- `format` 由副檔名推定；副檔名不在 `{txt, md, pdf}` 時視為 unsupported（skip，不建立 `RawSource`）。
- `relpath` **MUST NOT** 逸出 `/ks/raw_sources/`（防 path traversal）。

**狀態轉移**: immutable；修改等同新 version（不同 sha256），觸發 manifest 更新 + 舊 artifacts 覆寫。

---

## 2. `ManifestEntry` 與 `Manifest`

`/ks/manifest.json` 的單筆紀錄；串接來源與兩層衍生 artifacts，為 idempotency 與 prune 的依據。

```python
from dataclasses import dataclass, field

@dataclass
class DerivedArtifacts:
    wiki_pages: list[str] = field(default_factory=list)   # slug list
    vector_ids: list[str] = field(default_factory=list)   # chromadb id list

@dataclass
class ManifestEntry:
    relpath: str
    sha256: str
    format: Format
    size_bytes: int
    ingested_at: str                   # ISO 8601
    derived: DerivedArtifacts = field(default_factory=DerivedArtifacts)

@dataclass
class Manifest:
    version: int                        # schema 版本，Phase 1 = 1
    entries: dict[str, ManifestEntry]   # key = relpath
```

**驗證規則**:
- Manifest 寫入採 atomic：寫至 `/ks/manifest.json.tmp` → `os.replace()`，避免中斷損毀。
- 若 `/ks/manifest.json` 遺失但 `wiki/`、`vector/db/` 仍在 → ingest `resume_or_rebuild()` 從 `raw_sources/` hash 重建 manifest。

**狀態轉移**:
- 新檔: `entries[relpath]` 不存在 → 建立 `ManifestEntry`、ingest 兩層。
- Hash 相同: `entries[relpath].sha256 == new_hash` → skip（idempotent）。
- Hash 變更: 覆寫 `DerivedArtifacts`；先刪除舊 wiki/vector artifacts 再寫入新。
- 檔案遺失: 預設保留；`--prune` 會刪除對應 entry 與 artifacts。

---

## 3. `WikiPage`

落地於 `/ks/wiki/pages/<slug>.md`。

```python
@dataclass
class WikiPage:
    slug: str
    title: str
    summary: str           # 一行摘要（供 index.md）
    body: str              # markdown 本文
    source_relpath: str    # 對應 RawSource.relpath（若為 write-back 產出則 = "<writeback>"）
    origin: Literal["ingest", "writeback"]
    updated_at: str        # ISO 8601
```

**Markdown 檔案格式**（以 YAML frontmatter 帶中繼資料）:

```markdown
---
slug: project-a
title: 專案 A
summary: A 專案的規劃、里程碑與已知風險
source: raw_sources/project-a.md
origin: ingest
updated_at: 2026-04-23T14:32:00+08:00
---

# 專案 A

（body 內容）
```

**驗證規則**:
- `slug` 由 `python-slugify` 生成；碰撞時加 `-<n>` 後綴（`project-a` → `project-a-2`）。
- `slug` 格式: `re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)`。
- 非 ASCII 檔名經音譯；若音譯後為空（極端 emoji），fallback 為 `untitled-<sha8>`。

---

## 4. `WikiIndexEntry`

`/ks/wiki/index.md` 中的一行 TOC；非持久化物件，序列化為 markdown line。

**Markdown 格式**:

```markdown
- [專案 A](pages/project-a.md) — A 專案的規劃、里程碑與已知風險
```

**Python 表示**（讀取時用）:

```python
@dataclass(frozen=True)
class WikiIndexEntry:
    slug: str
    title: str
    summary: str
```

**一致性規則**:
- Index 必須與 `pages/` 檔案 1:1 對應，無 orphan、無 dead link。`storage/wiki.py` 在每次寫入後呼叫 `reconcile()` 驗證。

---

## 5. `LogEntry`

`/ks/wiki/log.md` append-only 營運紀錄；ingest 與 write-back 都會追加。

**Markdown 格式**（比照 [docs/main.md §8.2](../../docs/main.md)）:

```markdown
## 2026-04-23 14:30 | ingest | skipped
- target: raw_sources/project-a.md
- reason: hash unchanged
```

```markdown
## 2026-04-23 14:32 | writeback | committed
- query: 專案A目前風險是什麼
- route: wiki
- source: [wiki, vector]
- pages touched: pages/project-a.md
- confidence: 0.87
```

**Python 表示**:

```python
from dataclasses import field
from typing import Literal

Route = Literal["wiki", "vector"]
EventType = Literal["ingest", "writeback"]
EventStatus = Literal[
    "created", "updated", "skipped", "unsupported", "failed",
    "committed", "declined", "skip-non-tty",
]

@dataclass(frozen=True)
class LogEntry:
    timestamp: str                         # ISO 8601
    event: EventType
    status: EventStatus
    target: str | None = None             # ingest 事件必填
    reason: str | None = None             # skipped / unsupported / failed 原因
    query: str | None = None              # writeback 事件必填
    route: Route | None = None
    source: list[Route] = field(default_factory=list)
    pages_touched: list[str] = field(default_factory=list)
    confidence: float | None = None       # [0.0, 1.0]
```

**驗證規則**:
- `event="ingest"` 時，`target` 必填；`status` 限 `created|updated|skipped|unsupported|failed`。
- `event="writeback"` 時，`query` 必填；`status` 限 `committed|declined|skip-non-tty|failed`。
- `route` / `source` 若出現，限 `wiki` / `vector`（憲法 §I / §II）。
- `confidence` 若出現，值域 ∈ [0.0, 1.0]。
- 寫入失敗（例如磁碟滿）時，log 本身無法追加 → fallback 至 stderr warning，並回 exit `1`。

---

## 6. `VectorChunk`

落地於 chromadb collection；不直接以 JSON 檔儲存。

```python
@dataclass
class VectorChunk:
    id: str                # manifest 中 vector_ids 所記之 id：<sha8>-<chunk_idx>
    text: str              # normalized chunk 文字
    embedding: list[float] # 由 chromadb 管理，不手動序列化
    metadata: dict         # {source_relpath, chunk_idx, tokens, format, sha256_source}
```

**chromadb collection 設定**:
- Collection 名: `hks_phase1`
- Distance: `cosine`（用於 `confidence`）
- Embedding function: `SentenceTransformerEmbeddingFunction(model_name=<HKS_EMBEDDING_MODEL>)`

**Chunking 規則**:
- `chunk_size = 512 tokens`、`overlap = 64 tokens`；以 MiniLM `AutoTokenizer` 計算。
- 切點偏好段落 / 句子邊界（以 double newline / `。` / `.` 為候選），保守 fallback 為硬切。

---

## 7. `RoutingRule`

`config/routing_rules.yaml` 的一條規則。

**YAML 格式**（範例）:

```yaml
version: 1
default_route: vector
rules:
  - id: summary
    priority: 10
    target_route: wiki
    phase2_note: false
    keywords:
      zh:
        - 總結
        - 摘要
        - 概述
        - 重點
        - 報告
      en:
        - summary
        - summarize
        - overview
        - tl;dr
  - id: relation
    priority: 20
    target_route: vector       # Phase 1 fallback；Phase 2 改 graph
    phase2_note: true           # 觸發 "深度關係推理將於 Phase 2 支援" 附註
    keywords:
      zh: [影響, 關係, 依賴, 為什麼, 原因, 受影響]
      en: [impact, relation, depends, dependency, why, because]
  - id: detail
    priority: 30
    target_route: vector
    phase2_note: false
    keywords:
      zh: [原文, 細節, 條款, 片段, 引用]
      en: [excerpt, detail, clause, passage, verbatim]
```

**Python 表示**:

```python
@dataclass(frozen=True)
class RoutingRule:
    id: str
    priority: int                    # 小 = 高優先；衝突時最低數字勝出
    target_route: Route
    phase2_note: bool                # 是否附註「深度關係推理將於 Phase 2 支援」
    keywords_zh: tuple[str, ...]
    keywords_en: tuple[str, ...]

@dataclass(frozen=True)
class RoutingRuleSet:
    version: int
    default_route: Route
    rules: tuple[RoutingRule, ...]   # 以 priority 升序排序
```

**驗證規則**:
- `target_route` ∈ `{wiki, vector}`；graph 不允許。
- `priority` unique。
- `keywords_*` 至少 1 個；比對時先轉 lowercase 並以「子字串包含」判定。

**匹配演算法**:
1. query 字串 lowercase，zh 保留原形。
2. 依 `priority` 升序迭代每條 rule；第一條命中（zh 或 en 任一 keyword 命中）即返回。
3. 全未命中 → `default_route`。
4. 命中紀錄寫入 `TraceStep(kind="rule_match", rule_id=..., keyword=..., target=...)`。

---

## 8. `QueryResponse` 與 `TraceStep`（對外 JSON schema）

憲法 §II 規範之對外穩定介面。實體定義在 `core/schema.py`，schema 外部化於 [`contracts/query-response.schema.json`](./contracts/query-response.schema.json)。

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class TraceStep:
    kind: Literal[
        "rule_match", "wiki_lookup", "vector_lookup",
        "fallback", "merge", "writeback", "error",
        "ingest_summary",
    ]
    detail: dict                 # kind 特定資料；必為可 JSON 序列化

@dataclass
class Trace:
    route: Route                 # "wiki" | "vector"；Phase 1 禁 "graph"
    steps: list[TraceStep] = field(default_factory=list)

@dataclass
class QueryResponse:
    answer: str
    source: list[Route]          # ["wiki"] / ["vector"] / ["wiki","vector"]
    confidence: float            # [0.0, 1.0]
    trace: Trace
```

**欄位約束**（[`contracts/query-response.schema.json`](./contracts/query-response.schema.json) 為**權威來源**；以下為人類可讀摘要，與 schema 衝突時以 schema 為準）:
- `answer`: string，非空（schema `minLength: 1`）；錯誤情境填錯誤說明。
- `source`: array of `{wiki, vector}` enum；元素不得重複（schema `uniqueItems: true`）；可為空（`[]` 代表無命中）；`"graph"` **不允許**。
- `confidence`: number ∈ [0.0, 1.0]。
- `trace.route`: `{wiki, vector}` enum；`"graph"` **不允許**。
- `trace.steps`: array；order-preserving；每步 `kind`（限 `TraceStep` 8 值 Literal）+ `detail`（object，additional properties allowed）。

---

## 9. Entity 關係圖（Phase 1）

```
                        ingest
RawSource  ─────────▶  ManifestEntry
   │                   │
   │ parse+extract     │ derived
   ▼                   ▼
WikiPage           VectorChunk
   │                   │
   │ TOC               │ embedded in
   ▼                   ▼
WikiIndexEntry     chromadb collection
                       │
                       ▼ (on query)
                  QueryResponse ◀── TraceStep*
                       ▲
                       │ writeback (option)
                   LogEntry

RoutingRule ──────▶ router ──▶ TraceStep
(config)                          (embedded in QueryResponse.trace)
```

Phase 2 引入 graph 時，預期改動點（非本 feature 範圍）:
- `WikiPage` 新增 `entities` / `relations` 欄位
- 新增 `GraphNode` / `GraphEdge` Entity
- `QueryResponse.source` enum 擴充 `graph`
- `RoutingRule.target_route` enum 擴充 `graph`

以上皆屬憲法 §II MINOR（新增允許值），與 Phase 1 契約保持前向相容。
