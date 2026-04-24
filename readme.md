# Hybrid Knowledge System (HKS)

[English](./README.en.md)

Hybrid Knowledge System 是一個 CLI-first、domain-agnostic 的知識系統。現在的 runtime 已完成 Phase 2：ingest 支援 `txt / md / pdf / docx / xlsx / pptx`，query 會在 `wiki / graph / vector` 三層間切換，relation 類問題優先走 graph，高 confidence 答案預設自動 write-back。

## 目前能做什麼

- `ks ingest <file|dir> [--pptx-notes include|exclude]`：建立 `raw_sources/`、`wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json`
- `ks query "<question>" [--writeback auto|yes|no|ask]`：回傳穩定 JSON，summary 優先 wiki、relation 優先 graph、detail 優先 vector
- `ks lint`：仍為 Phase 3 stub
- 獨立圖片檔 ingest 尚未實作；後續 Phase 3 spec 才會凍結可接受的 raster formats、normalize / 轉檔策略與 OCR / VLM 流程

## 5 分鐘上手

```bash
mise install
uv sync
make fixtures
export KS_ROOT=$(mktemp -d /tmp/hks.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks query "這批文件的重點是什麼" --writeback=no | jq .
uv run ks query "A 專案延遲會影響哪些系統" --writeback=no | jq .
cat "$KS_ROOT/graph/graph.json" | jq '.nodes | length, .edges | length'
```

## 怎麼使用

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

- 支援 `txt`、`md`、`pdf`、`docx`、`xlsx`、`pptx`
- 以 `SHA256 + parser_fingerprint` 做 idempotency
- `--pptx-notes=exclude` 會改變 parser fingerprint，觸發 pptx re-ingest
- 目前不接受獨立圖片檔；不要把 `png` / `jpg` / `heic` / `webp` 視為已承諾支援

### Query

```bash
uv run ks query "<question>" [--writeback auto|yes|no|ask]
```

- summary / overview 類：優先 wiki
- relation / impact / dependency / why 類：優先 graph，miss 才 fallback vector
- detail / clause 類：優先 vector
- 無命中仍 exit `0`，只是 `source=[]`

### Write-back

- `auto`：預設模式；`confidence >= HKS_WRITEBACK_AUTO_THRESHOLD` 時自動寫回 wiki
- `yes`：強制寫回
- `no`：永不寫回
- `ask`：保留舊互動模式；TTY 才詢問，非 TTY 會 skip

自動 write-back 產生的新頁面會帶 `## Related`，連回這次答案涉及的既有 wiki pages。  
automation / agent workflow 仍建議顯式帶 `--writeback=no`，避免測試或批次流程產生多餘頁面。

### Lint

```bash
uv run ks lint
```

仍是固定 JSON stub；真正 lint 系統留到 Phase 3。

## 輸出格式

```json
{
  "answer": "...",
  "source": ["graph"],
  "confidence": 0.88,
  "trace": {
    "route": "graph",
    "steps": [
      {"kind": "routing_model", "detail": {}},
      {"kind": "graph_lookup", "detail": {}}
    ]
  }
}
```

`ks ingest`、`ks query`、`ks lint` 共用同一 top-level JSON shape。

## Exit Code

- `0`：成功，包含 query 無命中
- `1`：一般錯誤
- `2`：CLI usage error
- `65`：ingest data error
- `66`：輸入不存在，或 `KS_ROOT` 尚未初始化

## 常用環境變數

- `KS_ROOT`：runtime 資料根，預設 `./ks`
- `HKS_EMBEDDING_MODEL`：embedding backend；`simple` 適合離線 smoke / CI
- `HKS_ROUTING_MODEL`：routing backend 標記與未來接本機 model 的入口；預設 `simple`
- `HKS_WRITEBACK_AUTO_THRESHOLD`：auto write-back 門檻，預設 `0.75`
- `HKS_OFFICE_MAX_FILE_MB`：Office 單檔 ingest 上限，預設 `200`
- `HKS_OFFICE_TIMEOUT_SEC`：Office parser timeout，預設 `60`
- `HKS_ROUTING_RULES`：覆寫 routing rules 檔案路徑

## 進一步文件

- Phase 1 基線：[specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- Office ingest 擴充：[specs/002-phase2-ingest-office/spec.md](./specs/002-phase2-ingest-office/spec.md)
- Phase 2 graph / routing / write-back：[specs/003-phase2-graph-routing/spec.md](./specs/003-phase2-graph-routing/spec.md)
- Phase 2 contract：[specs/003-phase2-graph-routing/contracts/query-response.schema.json](./specs/003-phase2-graph-routing/contracts/query-response.schema.json)
- Spec archive index：[specs/ARCHIVE.md](./specs/ARCHIVE.md)
- Phase 3 圖片 ingest 尚未成 spec；目前只確認它會是後續獨立工作，不沿用 `003` scope

## 開發檢查

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT
