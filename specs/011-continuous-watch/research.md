# Research: Continuous update / watch workflow

## Decision: Bounded scan/run/status instead of resident daemon

Decision: 011 MVP implements explicit `scan`, `run`, and `status` commands. It does not start a resident daemon or OS-specific filesystem watcher.

Rationale: HKS is local-first and CLI-first. A resident daemon would introduce lifecycle management, cross-platform watcher behavior, crash recovery, and user trust questions before the core refresh semantics are proven.

Alternatives considered:

- Resident daemon: rejected for MVP due process lifecycle and platform-specific watch complexity.
- Cron-only integration: rejected because it hides HKS state and does not help agents inspect refresh plans.

## Decision: Plan-first mutation boundary

Decision: `scan` is read-only. `run` defaults to dry-run semantics unless caller explicitly selects execution. Profiles control which existing pipeline capabilities may mutate state.

Rationale: Existing HKS write-back and 009 apply semantics are caller-explicit. Watch must not create a new path for silent wiki/graph/vector mutation.

Alternatives considered:

- Auto-apply any stale source immediately: rejected because source edits can cascade into wiki and graph pollution.
- Always execute full 008/009/010 refresh: rejected because users need narrower profiles for cost, latency, and safety.

## Decision: Store watch state as derived operational artifacts

Decision: Write watch plans, runs, latest pointer, and event log under `$KS_ROOT/watch/`.

Rationale: Watch state is operational evidence, not authoritative knowledge. Keeping it separate prevents query/routing semantics from changing and allows lint to validate partial/corrupt operational state.

Alternatives considered:

- Store watch state in manifest: rejected because manifest tracks source ingestion truth, not refresh orchestration history.
- Store watch state in coordination ledger: rejected because coordination is multi-agent handoff state, not source refresh lineage.

## Decision: Reuse existing command services for execution

Decision: Watch executor calls existing ingest, LLM extraction, wiki synthesis, and graphify services rather than duplicating pipeline logic.

Rationale: Parser fingerprint, provider gates, write-back rules, graphify idempotency, and adapter error mapping already live in established modules. Reimplementation would drift.

Alternatives considered:

- Directly mutate wiki/graph/vector artifacts from watch executor: rejected as duplicate ingestion pipeline logic.
- Shell out to CLI subprocesses: rejected because Python service calls preserve structured errors and testability.

## Decision: Dedicated watch lock

Decision: Bounded execution uses a dedicated watch lock, separate from ingest and coordination locks.

Rationale: Watch orchestrates multiple services and may hold state across action boundaries. A dedicated lock gives deterministic conflict errors without changing existing ingest or coordination semantics.

Alternatives considered:

- Reuse ingest lock only: rejected because watch also manages 008/009/010 refresh state.
- No lock: rejected because concurrent agents could interleave runs and corrupt latest pointers.

## Decision: Adapter parity from first implementation

Decision: CLI, MCP, and HTTP contracts are part of the initial 011 surface.

Rationale: 006 made adapters formal surfaces and 008-010 preserved parity. 011 must not create CLI-only drift that agents cannot invoke through the same local interfaces.

Alternatives considered:

- CLI-only MVP: rejected due existing adapter contract discipline.
