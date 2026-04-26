# Quickstart: Continuous update / watch workflow

## Prepare fixture runtime

```bash
export KS_ROOT="$(mktemp -d)"
export HKS_EMBEDDING_MODEL=simple
mkdir -p "$KS_ROOT/sources"
printf "Alpha owns Project Apollo.\n" > "$KS_ROOT/sources/a.md"
uv run ks ingest "$KS_ROOT/sources/a.md" | jq .
```

## Scan without mutation

```bash
printf "Alpha owns Project Apollo. Apollo depends on Beta.\n" > "$KS_ROOT/sources/a.md"
uv run ks watch scan --source-root "$KS_ROOT/sources" | jq .
```

Expected:

- response uses top-level `answer/source/confidence/trace`
- `trace.steps` contains `kind="watch_summary"`
- changed source is counted as `stale`
- no authoritative layer is changed by scan

## Scan raw_sources fallback

```bash
uv run ks watch scan | jq .
```

Expected:

- response still uses `trace.steps[kind="watch_summary"]`
- scan inspects `$KS_ROOT/raw_sources` only
- response does not claim external source roots were checked

## Dry-run a bounded refresh

```bash
uv run ks watch run --source-root "$KS_ROOT/sources" --mode dry-run --profile ingest-only | jq .
```

Expected:

- stores or returns a refresh plan
- no ingest, wiki apply, graphify store, or vector mutation is executed
- plan fingerprint is stable for unchanged inputs

## Execute ingest-only refresh

```bash
uv run ks watch run --source-root "$KS_ROOT/sources" --mode execute --profile ingest-only --requested-by codex | jq .
uv run ks watch status | jq .
```

Expected:

- stale source is re-ingested through existing ingest behavior
- watch run state is recorded under `$KS_ROOT/watch/`
- status reports latest run id and completed action counts

## Execute derived refresh

```bash
uv run ks watch run --source-root "$KS_ROOT/sources" --mode execute --profile derived-refresh --include-graphify --requested-by codex | jq .
```

Expected:

- refresh executes required ingest actions first
- graphify store runs only when explicitly enabled
- response links graphify artifacts through watch action output refs

## MCP / HTTP surface

Expected MCP tools:

- `hks_watch_scan`
- `hks_watch_run`
- `hks_watch_status`

Expected HTTP endpoints:

```bash
curl -s http://127.0.0.1:8766/watch/scan \
  -H 'content-type: application/json' \
  -d "{\"ks_root\":\"$KS_ROOT\",\"source_roots\":[\"$KS_ROOT/sources\"]}" | jq .

curl -s http://127.0.0.1:8766/watch/status \
  -H 'content-type: application/json' \
  -d "{\"ks_root\":\"$KS_ROOT\"}" | jq .
```

## Safety checks

```bash
uv run ks lint --strict | jq .
```

Expected:

- lint detects corrupt watch artifacts, partial watch runs, and latest pointer mismatch
- lint does not treat watch state as authoritative knowledge
