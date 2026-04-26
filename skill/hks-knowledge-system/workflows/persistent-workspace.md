# Persistent Workspace Workflow

用途：讓 OpenClaw / Claude / Codex 跨 session 重用同一個 HKS knowledge runtime。

HKS 的持久化知識庫不在 repo tracked files 裡；它存在 `KS_ROOT`。如果 agent 只 clone repo 或只安裝 skill，還沒有 knowledge runtime。

所有 agent 共用同一套 runtime 的最簡方式，是讓它們都 source 同一個檔案：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
```

如果本機已經有既有 runtime，可以用 ignored env file 設定預設值：

```bash
mkdir -p .hks-runs
cat > .hks-runs/shared-runtime.env <<'EOF'
export KS_ROOT="$HKS_REPO_ROOT/.hks-runs/work/ks"
export HKS_WORKSPACE_REGISTRY="$HKS_REPO_ROOT/.hks-runs/workspaces.json"
# Keep this aligned with the model used when the vector DB was built.
# Use `simple` for smoke-test runtimes or any runtime ingested with that model.
export HKS_EMBEDDING_MODEL=simple
EOF
```

`.hks-runs/shared-runtime.env` 不應提交；它是這台機器給所有 local agents 共用的指標。

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

## Identify The Active Runtime

當 agent 回答「沒有持久化知識庫」或看起來讀錯資料庫時，先要求它跑：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
echo "$KS_ROOT"
uv run ks source list
find "$KS_ROOT/wiki/pages" -maxdepth 1 -type f -name '*.md' | wc -l
```

不要只看 repo 裡是否有 `ks/`。`./ks` 是 fallback default，可能是另一套 ignored local runtime。

如果 `ks query` 回報 embedding dimension mismatch，代表 `HKS_EMBEDDING_MODEL` 跟建立 vector DB 時不同。把 `.hks-runs/shared-runtime.env` 裡的 `HKS_EMBEDDING_MODEL` 改回原本 ingest 使用的 model；smoke-test/runtime demo 通常是 `simple`。
