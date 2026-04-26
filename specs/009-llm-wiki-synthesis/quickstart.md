# Quickstart: LLM-assisted wiki synthesis

> This quickstart describes expected 009 behavior after implementation.

## Prepare an 008 extraction artifact

```bash
export KS_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/hks-009.XXXXXX")
export HKS_EMBEDDING_MODEL=simple

uv run ks ingest tests/fixtures/valid
uv run ks llm classify project-atlas.txt --provider fake --mode store | jq .
```

Expected behavior:

- `$KS_ROOT/llm/extractions/` contains one valid 008 artifact.
- The 009 commands below consume that artifact; they do not re-run extraction implicitly.

## Preview a wiki page candidate

```bash
uv run ks wiki synthesize --source-relpath project-atlas.txt --mode preview --provider fake | jq .
```

Expected behavior:

- stdout uses the HKS top-level JSON response shape.
- `trace.steps` contains `kind="wiki_synthesis_summary"`.
- response includes candidate title, summary, body, target slug, diff summary, confidence, and lineage back to the 008 extraction artifact.
- `wiki/`, `graph/graph.json`, `vector/db/`, and `manifest.json` remain unchanged.

## Store a wiki synthesis candidate

```bash
uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake | jq .
CANDIDATE_ID=$(uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas-synthesis --mode store --provider fake \
  | jq -r '.trace.steps[] | select(.kind=="wiki_synthesis_summary").detail.artifact.artifact_id')
find "$KS_ROOT/llm/wiki-candidates" -maxdepth 1 -type f -name '*.json'
```

Expected behavior:

- response includes a candidate artifact reference.
- stored candidate artifact validates against `contracts/wiki-synthesis-artifact.schema.json`.
- authoritative wiki pages remain unchanged.

## Apply a wiki synthesis candidate

```bash
uv run ks wiki synthesize --candidate-artifact-id "$CANDIDATE_ID" --mode apply --provider fake | jq .
find "$KS_ROOT/wiki/pages" -maxdepth 1 -type f -name '*.md'
tail -40 "$KS_ROOT/wiki/log.md"
```

Expected behavior:

- exactly one wiki page is created or updated.
- `wiki/index.md` is rebuilt.
- `wiki/log.md` records the apply operation and provenance.
- graph, vector, manifest, and 008 extraction artifacts remain unchanged.
- repeating the same apply after a successful write returns an idempotent result instead of rewriting unrelated content.

## MCP usage

```json
{
  "source_relpath": "project-atlas.txt",
  "mode": "preview",
  "provider": "fake"
}
```

Expected MCP tool:

- `hks_wiki_synthesize`
- success payload matches CLI response semantics.
- stale artifact, provider, and candidate validation failures are returned as structured adapter errors.

## HTTP usage

```bash
uv run hks-api --host 127.0.0.1 --port 8766
curl -s http://127.0.0.1:8766/wiki/synthesize \
  -H 'content-type: application/json' \
  -d '{"source_relpath":"project-atlas.txt","mode":"preview","provider":"fake"}' | jq .
```

Expected behavior:

- endpoint is loopback-only by default.
- success payload uses the same HKS top-level response shape.
- errors use the existing adapter error envelope.

## Missing artifact failure path

```bash
uv run ks wiki synthesize --source-relpath missing.md --mode preview
```

Expected behavior:

- command exits `66` with parseable JSON.
- response points caller to `ks llm classify <source-relpath> --mode store`.

## Missing stored candidate failure path

```bash
uv run ks wiki synthesize --candidate-artifact-id missing-candidate --mode apply
```

Expected behavior:

- command exits `66` with parseable JSON.
- response points caller to run `ks wiki synthesize --mode store` first and apply the returned candidate artifact id.

## Stale artifact failure path

```bash
printf '\nchanged\n' >> "$KS_ROOT/raw_sources/project-atlas.txt"
uv run ks ingest "$KS_ROOT/raw_sources/project-atlas.txt"
uv run ks wiki synthesize --source-relpath project-atlas.txt --mode preview
```

Expected behavior:

- command exits `65` with parseable JSON.
- no candidate artifact or wiki page is written.

## Slug conflict failure path

```bash
uv run ks llm classify project-atlas.txt --provider fake --mode store | jq .
CANDIDATE_CONFLICT_ID=$(uv run ks wiki synthesize --source-relpath project-atlas.txt --target-slug project-atlas --mode store --provider fake \
  | jq -r '.trace.steps[] | select(.kind=="wiki_synthesis_summary").detail.artifact.artifact_id')
mkdir -p "$KS_ROOT/wiki/pages"
printf '%s\n' '---' 'title: Project Atlas' 'origin: ingest' '---' > "$KS_ROOT/wiki/pages/project-atlas.md"
uv run ks wiki synthesize --candidate-artifact-id "$CANDIDATE_CONFLICT_ID" --mode apply
```

Expected behavior:

- command reports conflict and does not overwrite the non-`llm_wiki` page.
- graph, vector, manifest, and 008 extraction artifacts remain unchanged.

## Hosted provider opt-in failure path

```bash
unset HKS_LLM_NETWORK_OPT_IN
uv run ks wiki synthesize --source-relpath project-atlas.txt --mode preview --provider openai
```

Expected behavior:

- command exits `2` with parseable JSON.
- no candidate artifact or wiki page is written.
