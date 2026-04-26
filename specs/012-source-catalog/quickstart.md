# Quickstart: Source catalog and workspace selection

## 1. Source catalog for one HKS runtime

```bash
export KS_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/hks-012-catalog.XXXXXX")
export HKS_EMBEDDING_MODEL=simple

uv run ks ingest tests/fixtures/valid
uv run ks source list | jq .
uv run ks source show project-atlas.txt | jq .
uv run ks source list --format md | jq .
```

Expected:

- `ks source list` returns manifest sources in deterministic relpath order.
- `trace.steps[0].kind == "catalog_summary"`.
- `wiki/`, `graph/graph.json`, `vector/db/`, `manifest.json`, and `watch/` remain unchanged after list/show.

## 2. Register two workspaces

```bash
export HKS_WORKSPACE_REGISTRY="${TMPDIR:-/tmp}/hks-012-registry-$RANDOM.json"
rm -f "$HKS_WORKSPACE_REGISTRY"

KS_A=$(mktemp -d "${TMPDIR:-/tmp}/hks-012-a.XXXXXX")
KS_B=$(mktemp -d "${TMPDIR:-/tmp}/hks-012-b.XXXXXX")

KS_ROOT="$KS_A" HKS_EMBEDDING_MODEL=simple uv run ks ingest tests/fixtures/valid
KS_ROOT="$KS_B" HKS_EMBEDDING_MODEL=simple uv run ks ingest tests/fixtures/office

uv run ks workspace register project-a --ks-root "$KS_A" --label "Project A"
uv run ks workspace register project-b --ks-root "$KS_B" --label "Project B"
uv run ks workspace list | jq .
uv run ks workspace use project-a | jq .
```

Expected:

- Workspace list shows both records with resolved roots and source counts.
- `workspace use` returns an `export_command`; it does not mutate the current shell.

## 3. Query selected workspace

```bash
uv run ks workspace query project-a "這批文件的重點是什麼" --writeback=no | jq .
uv run ks workspace query project-b "這批文件的重點是什麼" --writeback=no | jq .
```

Expected:

- Query results come from the selected workspace only.
- Response shape matches existing `ks query`.

## 4. Adapter smoke

```bash
uv run hks-mcp --help
uv run hks-api --help
```

Expected 012 adapter surface:

- MCP tools expose source list/show and workspace list/register/remove/use/query.
- HTTP exposes `/catalog/sources`, `/catalog/sources/{relpath}`, `/workspaces`, `/workspaces/{id}`, and `/workspaces/{id}/query`.
