# Hybrid Knowledge System (HKS)

[English](./README.en.md)

Hybrid Knowledge System 是一個 CLI-first、domain-agnostic 的知識系統。Phase 1 已落地的 runtime 會把 txt / md / pdf 文件同步整理成 wiki 與 vector store，並透過 rule-based routing 回答 query。Graph 明確延後到 Phase 2；Phase 1 的 JSON、route 與 runtime path 都不允許出現 graph code path。

## Phase 1 目前能做什麼

- `ks ingest <file|dir>`：匯入 txt / md / pdf，建立 `raw_sources/`、`wiki/`、`vector/db/`、`manifest.json`
- `ks query "<question>" [--writeback ask|yes|no]`：回傳穩定 JSON，並依 TTY / flag 決定是否 write-back
- `ks lint`：Phase 1 stub，保留 Phase 3 介面

## 5 分鐘上手

### 1. 安裝依賴

```bash
mise install
uv sync
uv run ks --help
```

### 2. 建立乾淨 runtime

```bash
export KS_ROOT=$(mktemp -d /tmp/hks.XXXXXX)
export HKS_EMBEDDING_MODEL=simple
```

`HKS_EMBEDDING_MODEL=simple` 適合 smoke test、CI、離線驗證。要用真實 multilingual embedding 時，移除這個變數即可，系統會改用預設模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。

### 3. 匯入文件

```bash
uv run ks ingest tests/fixtures/valid
```

成功後會在 `KS_ROOT` 下看到：

```text
raw_sources/
wiki/
vector/
manifest.json
```

### 4. 開始查詢

```bash
uv run ks query "這批文件的重點是什麼" --writeback=no | jq .
uv run ks query "clause 3.2 text" --writeback=no | jq .
uv run ks query "A 專案延遲會影響哪些系統" --writeback=no | jq .
uv run ks lint | jq .
```

### 5. 看生成結果

```bash
cat "$KS_ROOT/wiki/index.md"
tail -n 20 "$KS_ROOT/wiki/log.md"
ls "$KS_ROOT/wiki/pages"
```

## 怎麼使用

### Ingest

```bash
uv run ks ingest <file-or-dir>
```

- 接受單檔或資料夾
- 支援 `txt`、`md`、`pdf`
- 同步更新 `raw_sources/`、`wiki/`、`vector/db/`、`manifest.json`
- 同內容重複 ingest 會依 SHA256 skip；只改一份文件時，只更新那一份的 derived artifacts

### Query

```bash
uv run ks query "<question>" [--writeback ask|yes|no]
```

- summary 類問題優先走 wiki
- detail / clause 類問題優先走 vector
- relation / impact 類問題在 Phase 1 仍走 vector fallback，答案會附上「深度關係推理將於 Phase 2 支援」
- 沒命中也會 exit `0`，只是 `source=[]`、`confidence=0.0`

### Write-back

- `ask`：TTY 互動時詢問；非 TTY 自動 skip
- `yes`：直接回寫 wiki
- `no`：永不回寫

在 automation / agent workflow 裡，預設用 `--writeback=no` 最穩，避免互動 prompt 卡住流程。

### Lint

```bash
uv run ks lint
```

Phase 1 只回固定 JSON stub；真正 lint 能力留到 Phase 3。

## 輸出格式

`ks query` 與 `ks lint` 的 stdout 都是單一 JSON object：

```json
{
  "answer": "...",
  "source": ["wiki", "vector"],
  "confidence": 0.87,
  "trace": {
    "route": "vector",
    "steps": []
  }
}
```

Phase 1 的 `source` 與 `trace.route` 不會出現 `graph`。

## Exit Code

- `0`：成功，包含 query 無命中
- `1`：一般錯誤
- `2`：CLI usage error
- `65`：ingest data error
- `66`：輸入不存在，或 `KS_ROOT` 尚未初始化

完整契約見 [specs/001-phase1-cli-mvp/contracts/cli-exit-codes.md](./specs/001-phase1-cli-mvp/contracts/cli-exit-codes.md)。

## 常用環境變數

- `KS_ROOT`：runtime 資料根，預設 `./ks`
- `HKS_EMBEDDING_MODEL`：覆寫 embedding 模型；可設成 `simple` 做 deterministic fallback
- `HKS_MAX_FILE_MB`：單檔 ingest 上限，預設 `200`
- `HKS_ROUTING_RULES`：覆寫 routing rules 檔案路徑
- `NO_COLOR`：停用 stderr 彩色輸出

## 推薦工作流程

1. 先用 `KS_ROOT=$(mktemp -d ...)` 建一個隔離 runtime。
2. 第一次先 `uv run ks ingest <dir>`，確認 `manifest.json`、`wiki/index.md`、`vector/db/` 都有生成。
3. automation / agent 一律先用 `uv run ks query "<q>" --writeback=no`。
4. 人工整理知識時，才改用 `ask` 或 `yes` 讓 query 結果寫回 wiki。

## 進一步文件

- 規格：[specs/001-phase1-cli-mvp/spec.md](./specs/001-phase1-cli-mvp/spec.md)
- 設計：[specs/001-phase1-cli-mvp/plan.md](./specs/001-phase1-cli-mvp/plan.md)
- 詳細安裝 / 測試 / E2E：[specs/001-phase1-cli-mvp/quickstart.md](./specs/001-phase1-cli-mvp/quickstart.md)
- JSON 契約：[specs/001-phase1-cli-mvp/contracts/query-response.schema.json](./specs/001-phase1-cli-mvp/contracts/query-response.schema.json)

## 開發檢查

提交前至少跑：

```bash
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

## License

MIT
