# Watch Refresh Workflow

用途：對明確 source root 做 bounded scan / refresh。這不是 daemon，也不是 OS filesystem watcher。

Read-only planning：

```bash
export SOURCE_DIR="${SOURCE_DIR:-tests/fixtures/valid}"
uv run ks watch scan --source-root "$SOURCE_DIR"
uv run ks watch run --source-root "$SOURCE_DIR" --mode dry-run --profile ingest-only
uv run ks watch status
```

Execute refresh，只有使用者明確要求才做：

```bash
uv run ks watch run --source-root "$SOURCE_DIR" --mode execute --profile ingest-only
uv run ks lint --strict
```

不要把 `watch scan` 解讀成背景服務已啟動；它只是 bounded command。
