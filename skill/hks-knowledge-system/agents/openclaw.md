# OpenClaw Agent Guide: HKS

Use `../SKILL.md` first, then `../README.md` for the full framework. This file gives OpenClaw a short `ks` capability map.

## Repo Capability Map

- Knowledge ingest: `ks ingest`
- Query and routing: `ks query`
- Source catalog: `ks source list|show`
- Workspace selection: `ks workspace register|list|show|remove|use|query`
- Consistency checks: `ks lint`
- Multi-agent coordination: `ks coord session|lease|handoff|status|lint`
- Candidate extraction: `ks llm classify`
- Wiki candidate and apply: `ks wiki synthesize`
- Derived graph analysis: `ks graphify build`
- Bounded refresh workflow: `ks watch scan|run|status`

Adapter usage is documented separately in `../../../mcp/README.md`; do not treat MCP/HTTP as the default path.

## Deep References

- Full command map: `../commands/cli.md`
- Safe workflows: `../workflows/`
- Mutation policy: `../policies/safety.md`
- Response contract: `../contracts/response-contract.md`
- Troubleshooting: `../troubleshooting.md`

## Safety Defaults

- Use temporary `KS_ROOT` for experiments.
- Use `HKS_EMBEDDING_MODEL=simple` for deterministic smoke tests.
- Prefer preview/store modes before apply/execute modes.
- Do not treat `source=[]` as no-hit unless the command is actually `ks query`.
- Do not call `hsk`; that is not the CLI.

## Smoke Test

```bash
export KS_ROOT="$(mktemp -d /tmp/hks-openclaw.XXXXXX)"
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
uv run ks query "這批資料的重點是什麼？" --writeback=no
uv run ks source list
uv run ks graphify build --mode preview --provider fake
uv run ks lint --strict
```
