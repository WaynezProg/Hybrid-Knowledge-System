# Quickstart: Graphify pipeline

> This quickstart describes expected 010 behavior after implementation.

## Prepare a knowledge base

```bash
export KS_ROOT=$(mktemp -d /tmp/hks-010.XXXXXX)
export HKS_EMBEDDING_MODEL=simple

uv run ks ingest tests/fixtures/valid
uv run ks llm classify project-atlas.txt --provider fake --mode store | jq .
uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake | jq .
CANDIDATE_ID=$(uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake \
  | jq -r '.trace.steps[] | select(.kind=="wiki_synthesis_summary").detail.artifact.artifact_id')
uv run ks wiki synthesize --candidate-artifact-id "$CANDIDATE_ID" --mode apply --provider fake | jq .
```

Expected behavior:

- `wiki/`, `graph/`, `vector/`, `manifest.json`, `llm/extractions/`, and `llm/wiki-candidates/` exist.
- 010 reads those layers but does not mutate them in preview/store.

## Preview Graphify output

```bash
uv run ks graphify build --mode preview --provider fake | jq .
```

Expected behavior:

- stdout uses HKS top-level JSON response shape.
- `trace.route="graph"`.
- `trace.steps` contains `kind="graphify_summary"`.
- response includes node count, edge count, community count, audit summary, input fingerprint, and proposed output paths.
- `wiki/`, `graph/graph.json`, `vector/db/`, `manifest.json`, 008 artifacts, and 009 artifacts remain unchanged.

## Store Graphify artifacts

```bash
uv run ks graphify build --mode store --provider fake | jq .
find "$KS_ROOT/graphify" -maxdepth 3 -type f | sort
```

Expected behavior:

- `$KS_ROOT/graphify/runs/<run-id>/graphify.json` exists.
- `$KS_ROOT/graphify/runs/<run-id>/communities.json` exists.
- `$KS_ROOT/graphify/runs/<run-id>/audit.json` exists.
- `$KS_ROOT/graphify/runs/<run-id>/manifest.json` exists.
- `$KS_ROOT/graphify/latest.json` points to the stored run.
- authoritative wiki/graph/vector/manifest remain unchanged.

## Store without HTML

```bash
uv run ks graphify build --mode store --no-html --provider fake | jq .
```

Expected behavior:

- JSON and Markdown report artifacts can still be produced.
- `graph.html` is omitted.

## MCP usage

```json
{
  "mode": "preview",
  "provider": "fake"
}
```

Expected MCP tool:

- `hks_graphify_build`
- success payload matches CLI response semantics.

## HTTP usage

```bash
uv run hks-api --host 127.0.0.1 --port 8766
curl -s http://127.0.0.1:8766/graphify/build \
  -H 'content-type: application/json' \
  -d '{"mode":"preview","provider":"fake"}' | jq .
```

Expected behavior:

- endpoint is loopback-only by default.
- success payload uses the same HKS top-level response shape.
- errors use the existing adapter error envelope.

## Missing runtime failure path

```bash
export KS_ROOT=$(mktemp -d /tmp/hks-010-empty.XXXXXX)
uv run ks graphify build --mode preview
```

Expected behavior:

- command exits `66` with parseable JSON.
- no graphify artifact is written.

## Hosted provider opt-in failure path

```bash
unset HKS_LLM_NETWORK_OPT_IN
uv run ks graphify build --mode preview --provider hosted-example
```

Expected behavior:

- command exits `2` with parseable JSON.
- no graphify artifact is written.
