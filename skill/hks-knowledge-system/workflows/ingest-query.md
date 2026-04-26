# Ingest And Query Workflow

用途：把資料放進 HKS，然後查詢。

```bash
export KS_ROOT="${KS_ROOT:-$(mktemp -d "${TMPDIR:-/tmp}/hks-runtime.XXXXXX")}"
export SOURCE_DIR="${SOURCE_DIR:-tests/fixtures/valid}"
uv run ks ingest "$SOURCE_DIR"
uv run ks source list
uv run ks query "這批資料有哪些重點？" --writeback=no
uv run ks query "哪些項目互相依賴？" --writeback=no
uv run ks lint --strict
```

判斷 routing：

- summary 類問題優先 wiki。
- relation / dependency / impact 類問題優先 graph。
- detail / clause 類問題優先 vector。

注意：`ks ingest` 不會整理原始資料夾，不會重新命名或移動來源檔；它整理的是 `$KS_ROOT` 內的知識層。
