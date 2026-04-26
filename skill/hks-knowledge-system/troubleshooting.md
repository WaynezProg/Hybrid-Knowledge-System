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

注意：`.hks-runs/` 和 `testhks/` 被 `.gitignore` 忽略，不會跟著 repo clone 或 skill install 給其他 agent。

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
