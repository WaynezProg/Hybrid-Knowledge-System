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

## Session Memory / Workspace Status Query

查詢 session memory 的 workspace 狀態時，不要用口語名稱組自然語言 query。先 resolve workspace_id，再用明確格式。

```bash
# 1. resolve workspace_id
uv run ks workspace list
uv run ks source list
rg -n "workspace_id=" "$KS_ROOT/wiki/pages" "$KS_ROOT/raw_sources"

# 2. 用 workspace_id= prefix 查詢
uv run ks query "workspace_id=social-bank-check 最後處理到哪？" --writeback=no
uv run ks query "workspace_id=hks 最近完成什麼？" --writeback=no
uv run ks query "workspace_id=openclaw 2026-05-22 做了什麼？" --writeback=no
```

workspace_id resolve 失敗時才 fallback 到自然語言 query，並標記信心較低。
