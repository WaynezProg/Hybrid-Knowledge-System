# Quickstart: LLM-assisted classification and extraction

> This quickstart describes 008 runtime behavior.

## Preview one ingested source

```bash
export KS_ROOT=$(mktemp -d /tmp/hks-008.XXXXXX)
export HKS_EMBEDDING_MODEL=simple

uv run ks ingest tests/fixtures/valid
uv run ks llm classify project-atlas.txt --provider fake --mode preview | jq .
```

Expected behavior:

- stdout uses the HKS top-level JSON response shape.
- `trace.steps` contains `kind="llm_extraction_summary"`.
- response includes classification labels, summary candidate, key facts, entity candidates, relation candidates, confidence, source fingerprint, parser fingerprint, provider id, model id, and prompt version.
- `wiki/`, `graph/graph.json`, `vector/db/`, and existing manifest entries remain unchanged.

## Store an extraction artifact

```bash
uv run ks llm classify project-atlas.txt --provider fake --mode store | jq .
find "$KS_ROOT/llm/extractions" -type f -name '*.json' -maxdepth 1
```

Expected behavior:

- response includes an artifact reference.
- the stored JSON artifact validates against `contracts/llm-extraction-artifact.schema.json`.
- the artifact is keyed by source fingerprint, parser fingerprint, prompt version, provider id, and model id.
- store mode still does not apply changes to wiki, graph, or vector.

## MCP usage

```json
{
  "source_relpath": "project-atlas.txt",
  "mode": "preview",
  "provider": "fake"
}
```

Expected MCP tool:

- `hks_llm_classify`
- success payload matches CLI response semantics.
- provider and output validation failures are returned as structured adapter errors.

## HTTP usage

```bash
uv run hks-api --host 127.0.0.1 --port 8766
curl -s http://127.0.0.1:8766/llm/classify \
  -H 'content-type: application/json' \
  -d '{"source_relpath":"project-atlas.txt","mode":"preview","provider":"fake"}' | jq .
```

Expected behavior:

- endpoint is loopback-only by default.
- success payload uses the same HKS top-level response shape.
- errors use the existing adapter error envelope.

## Hosted provider safety (failure path)

Hosted providers are disabled unless explicitly configured via env vars. Implementation must fail closed when network opt-in or credentials are missing. CLI flags / MCP fields / HTTP body MUST NOT expose any opt-in toggle (see spec FR-022 and research Decision 6).

```bash
uv run ks llm classify project-atlas.txt --provider hosted-example --mode preview
```

Expected behavior without opt-in:

- command exits `2 USAGE` with a parseable JSON error (per FR-014 mapping).
- no provider call is attempted.
- no artifact is written.

## Hosted provider opt-in (gated but not implemented in 008)

```bash
export HKS_LLM_NETWORK_OPT_IN=1
export HKS_LLM_PROVIDER_HOSTED_EXAMPLE_API_KEY=<your-token>
# optional endpoint override:
# export HKS_LLM_PROVIDER_HOSTED_EXAMPLE_ENDPOINT=https://api.example.com/v1
uv run ks llm classify project-atlas.txt --provider hosted-example --mode preview | jq .
```

Expected behavior with opt-in in 008:

- the request passes the local-first gate, then exits `2 USAGE` because 008 ships only the deterministic `fake` provider.
- real hosted provider adapters are future optional extensions; they must preserve the same response shape, schema, and `trace.steps[kind="llm_extraction_summary"]` detail.
- if `HKS_LLM_NETWORK_OPT_IN` is unset OR the credential env var is missing, command exits `2 USAGE` earlier with parseable JSON and no provider call.
