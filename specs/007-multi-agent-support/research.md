# Research: Phase 3 階段三 — Multi-agent support

## Decision: 007 實作 coordination primitives，不實作 orchestration

- **Decision**: 007 only provides session, lease, handoff, status, and lint for local coordination.
- **Rationale**: HKS 的產品核心是 knowledge system，不是 agent runtime。Scheduler / supervisor / task planner 會引入任務分派、執行生命週期、權限與安全邊界，超出 Phase 3 多 agent 最小可用範圍。
- **Alternatives rejected**:
  - Agent process launcher：拒絕。這會讓 HKS 負責執行外部工具，安全面不合理。
  - Supervisor LLM：拒絕。會引入 hosted/local model decision loop，且難以離線穩定測試。
  - Task planner：拒絕。任務拆解是 agent 層工作，HKS 只提供共享狀態。

## Decision: CLI namespace 使用 `ks coord`

- **Decision**: New commands live under `ks coord`, not `ks agent`.
- **Rationale**: `coord` accurately describes coordination state. `agent` would imply HKS manages agent processes or identities.
- **Alternatives rejected**:
  - `ks agent ...`：拒絕。名稱暗示 authentication / execution ownership。
  - Add separate `hks-agent` entry point：拒絕。增加 surface，破壞 CLI-first simplicity。

## Decision: Ledger uses local JSON state + JSONL event log

- **Decision**: Persist state under `KS_ROOT/coordination/state.json` and append events to `KS_ROOT/coordination/events.jsonl`; protect writes with `KS_ROOT/coordination/.lock`.
- **Rationale**: Existing runtime already uses file-based local state. JSON keeps inspection/debug easy, JSONL provides append-only audit. File lock is sufficient for same-host local agents.
- **Alternatives rejected**:
  - SQLite：暫拒。It solves concurrency well, but adds a second persistence model before file-based semantics are proven.
  - Only JSONL replay, no state snapshot：拒絕。Status queries would require replaying all events every time.
  - Only mutable JSON, no events：拒絕。No audit trail and poor recovery story.

## Decision: Active ownership is lease-based with TTL

- **Decision**: Resource ownership is an expiring lease. Claim is atomic; renew extends expiry; release closes lease; expired leases no longer block new claims.
- **Rationale**: Agents can crash. Permanent lock ownership would require manual cleanup and would be fragile in multi-agent workflows.
- **Alternatives rejected**:
  - Permanent assignment：拒絕。Crash leaves resources blocked forever.
  - Advisory-only notes：拒絕。Cannot prevent duplicate work.
  - OS file locks per resource：拒絕。Not inspectable after process death and difficult to expose over MCP.

## Decision: `agent_id` is a local label, not identity

- **Decision**: `agent_id` is caller-provided and validated for format only. No auth, no RBAC, no trust boundary.
- **Rationale**: HKS is local-first single-user tooling. Pretending `agent_id` is security would be misleading.
- **Alternatives rejected**:
  - Token auth：拒絕。Belongs to a future remote/multi-user model, not local Phase 3.
  - OS user binding：拒絕。Agents often run as the same local user and need logical labels.

## Decision: Coordination detail gets its own schema

- **Decision**: Add `trace.steps.kind="coordination_summary"` and a dedicated `coordination-summary-detail.schema.json`.
- **Rationale**: Coordination output is neither lint nor ingest. A distinct step kind preserves machine parsing while keeping top-level `QueryResponse`.
- **Alternatives rejected**:
  - Encode everything in `answer` only：拒絕。Agents would parse natural language.
  - Reuse `lint_summary`：拒絕。Would blur operational coordination and consistency linting.

## Decision: MCP tools are MVP; HTTP coordination endpoints are optional P3

- **Decision**: CLI + MCP are required. HTTP facade is optional after MVP and must remain loopback-only if implemented.
- **Rationale**: 006 established MCP as agent-facing MVP. HTTP is useful for generic tooling but should not delay coordination correctness.
- **Alternatives rejected**:
  - CLI only：拒絕。Would regress 006’s agent integration path.
  - HTTP-first：拒絕。Misaligns with MCP-first integration and expands surface too early.
