# HKS HTTP Facade

Use this file for tools that call HKS over loopback HTTP.

Example JSON request bodies live in `examples/`.

## Start

```bash
uv run hks-api --host 127.0.0.1 --port 8766
```

## Common Requests

```bash
curl -sS http://127.0.0.1:8766/query \
  -H 'content-type: application/json' \
  -d '{"question":"Project Atlas summary","writeback":"no","ks_root":null}'
```

```bash
curl -sS http://127.0.0.1:8766/ingest \
  -H 'content-type: application/json' \
  -d '{"path":"tests/fixtures/valid","ks_root":null}'
```

```bash
curl -sS http://127.0.0.1:8766/watch/scan \
  -H 'content-type: application/json' \
  -d '{"source_roots":["tests/fixtures/valid"],"ks_root":null}'
```

## Notes

- The server is not meant to be always-on.
- The default host is loopback.
- Error responses use the adapter error envelope, not the CLI payload.
