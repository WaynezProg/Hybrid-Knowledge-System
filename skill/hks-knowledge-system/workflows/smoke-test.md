# Smoke Test Workflow

用途：確認 HKS CLI runtime 可用，且不碰使用者真實知識庫。

```bash
cd /Users/waynetu/claw_prog/projects/09-HKS
export KS_ROOT="$(mktemp -d /tmp/hks-smoke.XXXXXX)"
export HKS_EMBEDDING_MODEL=simple
uv run ks --help
uv run ks ingest tests/fixtures/valid
uv run ks source list
uv run ks query "這批資料的重點是什麼？" --writeback=no
uv run ks lint --strict
```

完成標準：

- `ks --help` 顯示 command list。
- ingest 成功建立 `manifest.json`、`wiki/`、`graph/`、`vector/`。
- query 回傳 schema-valid JSON。
- lint strict 沒有 error exit。
