# Response Contract

CLI success payloads share this top-level JSON shape:

```json
{
  "answer": "...",
  "source": ["wiki"],
  "confidence": 0.88,
  "evidence": [
    {
      "source_relpath": "atlas.txt",
      "route": "wiki",
      "quote": "original source snippet"
    }
  ],
  "trace": {
    "route": "wiki",
    "steps": []
  }
}
```

## Source Semantics

`source` only allows stable HKS layers:

```text
wiki
graph
vector
page_tree
```

Do not add `graphify`, `watch`, `catalog`, or `workspace` to top-level `source`.

## Evidence

`evidence[]` lists provenance for the winning candidate:

- Required fields: `source_relpath`, `route`, `quote`
- Optional fields: `section_path` (vector / page_tree), `page_range` (PDF)
- Evidence only describes the selected answer candidate, not all fused retrieval candidates

## `source=[]` Is Not Always No-Hit

Interpret by command:

- `ks query` with `source=[]` is a genuine no-hit / no usable source.
- `ks llm classify --mode preview|store` with `source=[]` means candidate artifact produced.
- `ks wiki synthesize --mode preview|store` with `source=[]` means candidate produced, authoritative wiki untouched.
- `ks watch scan|status` with `source=[]` means operational state.
- `ks source list|show` with `source=[]` means catalog response.

## Adapter Error Boundary

CLI uses top-level HKS payload. MCP / HTTP adapter error envelope is documented in `mcp/`; it is not part of the CLI skill contract.
