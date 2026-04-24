# Data Model: Phase 2 階段二 — Graph / Routing / Auto Write-back

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-24

## 1. `QueryResponse`（Phase 2）

top-level shape 不變，只擴充 enum：

- `source`: `wiki | graph | vector`
- `trace.route`: `wiki | graph | vector`
- `trace.steps.kind`: 新增 `routing_model`、`graph_lookup`

## 2. `GraphNode`

```python
@dataclass(slots=True)
class GraphNode:
    id: str
    type: Literal["Person", "Project", "Document", "Event", "Concept"]
    label: str
    aliases: list[str]
    source_relpaths: list[str]
    wiki_slugs: list[str]
```

## 3. `GraphEdge`

```python
@dataclass(slots=True)
class GraphEdge:
    id: str
    relation: Literal["owns", "depends_on", "impacts", "references", "belongs_to"]
    source: str
    target: str
    source_relpath: str
    evidence: str
```

## 4. `GraphPayload`

`/ks/graph/graph.json`：

```json
{
  "version": 1,
  "nodes": {},
  "edges": {}
}
```

## 5. `ManifestEntry.derived`

新增：

- `graph_nodes`
- `graph_edges`

完整 derived artifacts：

- `wiki_pages`
- `graph_nodes`
- `graph_edges`
- `vector_ids`

## 6. Write-back 狀態

允許值：

- `committed`
- `auto-committed`
- `declined`
- `auto-skipped-low-confidence`
- `skip-non-tty`
