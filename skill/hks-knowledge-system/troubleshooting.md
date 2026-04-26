# Troubleshooting

## `hsk` 找不到

前提錯。正式 CLI 是 `ks`。

```bash
uv run ks --help
```

## MCP / HTTP 沒有在跑

這不代表功能沒實作。Adapters 是 on-demand entrypoints，不是常駐服務。Adapter 文件在 `mcp/`。

## Agent 說沒有持久化知識庫

通常不是 HKS 沒有持久化能力，而是 agent 沒有指到已初始化的 `KS_ROOT`。

檢查：

```bash
echo "$KS_ROOT"
uv run ks source list
```

建立可重用 runtime：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks ingest <source-dir>
uv run ks workspace register work --ks-root "$KS_ROOT" --label "Work"
```

注意：`.hks-runs/` 和其他 repo-local runtime 目錄被 `.gitignore` 忽略，不會跟著 repo clone 或 skill install 給其他 agent。

如果本機已經有一套要所有 agent 共用的 runtime，建立 `.hks-runs/shared-runtime.env`，讓 `shared-runtime.sh` 自動讀取：

```bash
mkdir -p .hks-runs
cat > .hks-runs/shared-runtime.env <<'EOF'
export KS_ROOT="$HKS_REPO_ROOT/.hks-runs/work/ks"
export HKS_WORKSPACE_REGISTRY="$HKS_REPO_ROOT/.hks-runs/workspaces.json"
export HKS_EMBEDDING_MODEL=simple
EOF
```

之後所有 agent 都先跑：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
```

## Query 產生 wiki page

你沒有關掉 write-back。探索查詢請用：

```bash
uv run ks query "<question>" --writeback=no
```

## LLM / Graphify 沒有改 wiki

這是正確行為。`preview` / `store` 只產生 candidate 或 derived artifacts。只有 `ks wiki synthesize --mode apply` 寫 authoritative wiki。

## Source folder 沒被整理

這是正確行為。`ks ingest` 整理 `$KS_ROOT` 內的 knowledge layers，不改原始資料夾。

## 測試要穩定重現

用 deterministic embedding：

```bash
export HKS_EMBEDDING_MODEL=simple
```

## `Collection expecting embedding with dimension ...`

原因：查詢時使用的 `HKS_EMBEDDING_MODEL` 跟 vector DB 建立時不同。

先確認：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
echo "$HKS_EMBEDDING_MODEL"
uv run ks query "smoke test" --writeback=no
```

若既有 runtime 是用 deterministic smoke-test 建的，請在 `.hks-runs/shared-runtime.env` 設：

```bash
export HKS_EMBEDDING_MODEL=simple
```

如果要改用 OpenAI embedding，請改用新的 `KS_ROOT` 重新 ingest：

```bash
cp config/hks.env.example config/hks.env
$EDITOR config/hks.env

export KS_ROOT="$HKS_REPO_ROOT/.hks-runs/openai/ks"
export HKS_EMBEDDING_MODEL=openai:text-embedding-3-small
```
