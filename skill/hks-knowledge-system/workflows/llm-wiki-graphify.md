# LLM Wiki And Graphify Workflow

用途：在已有 ingest 結果後，產生 LLM extraction、wiki candidate、Graphify derived artifacts。

先找 source relpath：

```bash
uv run ks source list
```

Preview，不寫 authoritative wiki：

```bash
uv run ks llm classify <source-relpath> --mode preview --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath> --target-slug <slug> --mode preview --provider fake
uv run ks graphify build --mode preview --provider fake
```

Store candidate artifacts：

```bash
uv run ks llm classify <source-relpath> --mode store --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath> --target-slug <slug> --mode store --provider fake
uv run ks graphify build --mode store --provider fake
```

Apply wiki candidate，只有使用者明確要求才做：

```bash
uv run ks wiki synthesize --candidate-artifact-id <candidate-id> --mode apply --provider fake
uv run ks lint --strict
```

邊界：

- `llm classify --mode store` 只寫 `$KS_ROOT/llm/extractions/`。
- `wiki synthesize --mode store` 只寫 `$KS_ROOT/llm/wiki-candidates/`。
- `graphify build` 只寫 `$KS_ROOT/graphify/`。
- 只有 `wiki synthesize --mode apply` 會寫 authoritative wiki。
