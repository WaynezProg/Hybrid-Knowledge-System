# Persistent Workspace Workflow

用途：讓 OpenClaw / Claude / Codex 跨 session 重用同一個 HKS knowledge runtime。

HKS 的持久化知識庫不在 repo tracked files 裡；它存在 `KS_ROOT`。如果 agent 只 clone repo 或只安裝 skill，還沒有 knowledge runtime。

## Create A Persistent Runtime

```bash
cd "$(git rev-parse --show-toplevel)"
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks ingest <source-dir>
uv run ks source list
uv run ks workspace register work --ks-root "$KS_ROOT" --label "Work"
```

`.hks-runs/` is intentionally ignored by git. It is local runtime data, not source code.

## Reuse Later

```bash
cd "$(git rev-parse --show-toplevel)"
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks workspace list
uv run ks workspace query work "今天有哪些新資料？" --writeback=no
```

Or set `KS_ROOT` directly:

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks query "目前知識庫有哪些重點？" --writeback=no
```

## Scheduled Agent Trigger

如果 agent 每天定時觸發更新，不需要重做全部：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks watch scan --source-root <source-dir>
uv run ks watch run --source-root <source-dir> --mode execute --profile ingest-only
```

`sha256 + parser_fingerprint` 會讓未變更檔案 skip，只更新新增或變更的來源。
