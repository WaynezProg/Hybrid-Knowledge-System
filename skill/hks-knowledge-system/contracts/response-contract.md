# Response Contract

CLI success payloads share this top-level JSON shape:

```json
{
  "answer": "...",
  "source": ["wiki", "graph", "vector"],
  "confidence": 0.0,
  "trace": {
    "route": "wiki|graph|vector",
    "steps": []
  }
}
```

## Source Semantics

`source` 只允許 stable HKS layers:

```text
wiki
graph
vector
```

不要新增 `graphify`、`watch`、`catalog`、`workspace` 到 top-level `source`。

## `source=[]` 不一定是 no-hit

必須依 command 解讀：

- `ks query` 的 `source=[]` 才接近 no-hit / no usable source。
- `ks llm classify --mode preview|store` 的 `source=[]` 表示產生 candidate artifact。
- `ks wiki synthesize --mode preview|store` 的 `source=[]` 表示產生 candidate，不寫 authoritative wiki。
- `ks watch scan|status` 的 `source=[]` 表示 operational state。
- `ks source list|show` 的 `source=[]` 表示 catalog response。

## Adapter Error Boundary

CLI 走 top-level HKS payload。MCP / HTTP adapter 錯誤 envelope 放在 `mcp/` 文件，不在 CLI skill 內展開。
