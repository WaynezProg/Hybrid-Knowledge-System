# Troubleshooting

## `hsk` 找不到

前提錯。正式 CLI 是 `ks`。

```bash
uv run ks --help
```

## MCP / HTTP 沒有在跑

這不代表功能沒實作。Adapters 是 on-demand entrypoints，不是常駐服務。Adapter 文件在 `mcp/`。

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
