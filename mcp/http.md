# HKS HTTP Facade

Use this file for tools that call HKS over loopback HTTP.

Example JSON request bodies live in `examples/`.

## Start

```bash
export HKS_API_TOKEN='replace-with-local-token'
export HKS_API_INGEST_ROOTS='fixtures=/Users/me/hks/tests/fixtures'
uv run hks-api --host 127.0.0.1 --port 8766
```

Set `HKS_API_TOKEN` before using mutating or writeback-capable endpoints. Set `HKS_API_INGEST_ROOTS` when HTTP clients need `/ingest`; HTTP ingest only accepts relative paths under configured roots. `source_root_id` is required when multiple roots are configured and optional with one root, but explicit IDs are recommended.

## Common Requests

```bash
curl -sS http://127.0.0.1:8766/query \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"question":"Project Atlas summary","writeback":"no","ks_root":null}'
```

```bash
curl -sS http://127.0.0.1:8766/ingest \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"source_root_id":"fixtures","path":"valid","ks_root":null}'
```

```bash
curl -sS http://127.0.0.1:8766/watch/scan \
  -H 'Host: 127.0.0.1' \
  -H "Authorization: Bearer $HKS_API_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"source_roots":["tests/fixtures/valid"],"ks_root":null}'
```

```bash
curl -sS http://127.0.0.1:8766/lint \
  -H 'Host: 127.0.0.1' \
  -H 'content-type: application/json' \
  -d '{"strict":false,"fix":"none","ks_root":null}'
```

## Notes

- The server is not meant to be always-on.
- The default host is loopback.
- Browser-origin mutating requests are rejected by default when they include `Origin` or `Sec-Fetch-Site`.
- Use CLI/MCP for trusted automation that needs arbitrary local path semantics.
- Error responses use the adapter error envelope, not the CLI payload.
