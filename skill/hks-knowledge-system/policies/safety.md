# Safety And Mutation Policy

## Environment

- 使用 `uv run ...`。
- 不用 `brew install python/node`、`nvm`、`pyenv`、`asdf`、curl installer。
- 需要 Python 版本變更時用 `mise use python@<version>`。
- 實驗設定 temporary `KS_ROOT`，避免污染使用者資料。

## Read-Only By Default

預設 read path：

```bash
uv run ks query "<question>" --writeback=no
uv run ks source list
uv run ks source show <source-relpath>
uv run ks llm classify <source-relpath> --mode preview --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath> --mode preview --provider fake
uv run ks graphify build --mode preview --provider fake
uv run ks watch scan --source-root <source-dir>
```

## Writes Derived Artifacts Only

- `ks llm classify --mode store`
- `ks wiki synthesize --mode store`
- `ks graphify build --mode store`
- `ks watch run --mode dry-run` writes operational plan/run state only

## Writes Authoritative Knowledge Layers

- `ks ingest`
- `ks query` when write-back is enabled and confidence passes threshold
- `ks wiki synthesize --mode apply`
- `ks watch run --mode execute --profile ingest-only`

## Coordination

多 agent 共用同一個 `KS_ROOT` 時，先 claim lease，再修改 shared artifact：

```bash
uv run ks coord session start <agent-id>
uv run ks coord lease claim <agent-id> <resource> --ttl-seconds 1800
```

`ks coord` 是 local coordination，不是 RBAC、auth 或 multi-user isolation。
