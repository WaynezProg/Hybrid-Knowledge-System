# Claude Agent Guide: HKS

Use `../SKILL.md` first, then `../README.md` for the full framework. This file is the minimal Claude / Claude Code entrypoint for `ks`.

## First Principles

- This repo is implemented, not pre-implementation. Phase 1-3 and 008-012 are complete.
- CLI entrypoint is `ks`, not `hsk`.
- Use `uv run ...`; do not install runtimes.
- Keep `KS_ROOT` explicit for tests and user workflows.
- Use `--writeback=no` unless the user explicitly wants wiki mutation.
- For HTTP or MCP adapter work, switch to `../../../mcp/README.md`.
- For reusable knowledge across sessions, read `../workflows/persistent-workspace.md`.
- To share the same runtime with other agents, source `../config/shared-runtime.sh` from the repo root.

## Main Commands

```bash
uv run ks --help
uv run ks ingest <file-or-dir>
uv run ks query "<question>" --writeback=no
uv run ks source list
uv run ks workspace list
uv run ks lint --strict
uv run ks llm classify <source-relpath> --mode preview --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath> --mode preview --provider fake
uv run ks graphify build --mode preview --provider fake
uv run ks watch scan --source-root <source-dir>
```

## Session Memory / Workspace Status Query

查詢「某個 workspace 最後處理到哪？」時，**先 resolve workspace_id，再用明確格式查詢**。不要把口語名稱（social-bank-check、HKS、OpenClaw）直接丟給 `ks query`。

```bash
# Step 1: resolve workspace_id
uv run ks workspace list
uv run ks source list
# 找不到時 grep：
rg -n "workspace_id=" "$KS_ROOT/wiki/pages" "$KS_ROOT/raw_sources"

# Step 2: 用 workspace_id= prefix 查詢
uv run ks query "workspace_id=social-bank-check 最後處理到哪？" --writeback=no
uv run ks query "workspace_id=hks 最近完成什麼？" --writeback=no
uv run ks query "workspace_id=openclaw 2026-05-22 做了什麼？" --writeback=no
```

- 預設 `--writeback=no`。
- 只有在無法 resolve workspace_id 時才 fallback 到自然語言 query，並在回覆中標記信心較低。

## Deep References

- Full command map: `../commands/cli.md`
- Safe workflows: `../workflows/`
- Persistent runtime setup: `../workflows/persistent-workspace.md`
- Mutation policy: `../policies/safety.md`
- Response contract: `../contracts/response-contract.md`
- Troubleshooting: `../troubleshooting.md`

## Before Claiming Done

```bash
uv run ruff check .
uv run mypy src/hks
uv run pytest --tb=short -q
```

If the task changes only docs or agent guidance, still run at least `uv run ks --help`, `ruff`, and `mypy` unless there is a concrete blocker.
