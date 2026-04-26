# Research: Source catalog and workspace selection

## Decisions

### R1. Manifest is the source catalog authority

Decision: Build `ks source list/show` from existing `manifest.json` and derived artifact references, with optional integrity checks against referenced files.

Rationale: Manifest already records relpath, format, sha256, size, ingested_at, parser_fingerprint, and derived artifacts. Reconstructing a separate catalog would duplicate truth and drift.

Rejected alternative: Create a second source database during ingest. Rejected because it adds consistency burden before a new data source is needed.

### R2. Workspace registry stores `KS_ROOT` references, not source folders

Decision: Workspace records point to HKS runtime roots containing `manifest.json`, not arbitrary raw source folders.

Rationale: The user's selection target is "which HKS to query". Source roots are handled by ingest/watch; query needs a runtime root with wiki/graph/vector/manifest.

Rejected alternative: Register raw folders and auto-ingest on query. Rejected because it violates ingest-time organization and would make query mutate state.

### R3. No implicit shell mutation

Decision: `ks workspace use <id>` returns the resolved root plus a shell-safe `export KS_ROOT=...` string; it does not claim to mutate the parent shell.

Rationale: A CLI child process cannot reliably change the caller's shell environment. Being explicit avoids false state and agent confusion.

Rejected alternative: Persist a global "current workspace" and make all commands implicitly use it. Rejected for MVP because hidden global selection can make agents query the wrong knowledge base.

### R4. Workspace-aware query is an explicit wrapper

Decision: Add `ks workspace query <id> "<question>"` and adapter equivalents that resolve the workspace id, set scoped `KS_ROOT`, and delegate to existing query.

Rationale: It completes the user journey without changing existing `ks query` semantics or adding a global option to every command in 012.

Rejected alternative: Add `--workspace` to all existing commands. Rejected because it expands blast radius; later specs can add global option if the wrapper proves insufficient.

### R5. Registry path is configurable and test-isolated

Decision: Use an explicit registry path resolver with environment override such as `HKS_WORKSPACE_REGISTRY`, defaulting to an OS-appropriate user config path.

Rationale: Tests need temp isolation; users need predictable local config. The registry is not part of any single `KS_ROOT`.

Rejected alternative: Store registry under the current repo or current `KS_ROOT`. Rejected because workspace registry must outlive and reference multiple runtimes.

### R6. Adapter parity follows existing local safety rules

Decision: Expose source/workspace list/show/register/remove/query through MCP and loopback HTTP, with path validation and adapter error envelope mapping consistent with existing adapter tools.

Rationale: Agent use is a primary HKS surface. CLI-only catalog would force agents back to reading files directly.

Rejected alternative: Only expose `ks_root` parameter on existing query tool. Rejected because it does not solve discoverability or workspace listing.
