# Data Model: Phase 3 階段三 — Multi-agent support

## Runtime Layout

007 introduces one new runtime directory under `KS_ROOT`:

```text
/ks
  /coordination
    state.json
    events.jsonl
    .lock
```

Rules:
- `coordination/` is operational state, not knowledge content.
- `state.json` is the current materialized snapshot.
- `events.jsonl` is append-only audit/replay history.
- `.lock` protects all writes and claim decisions.

## CoordinationState

Materialized snapshot stored in `coordination/state.json`.

Fields:
- `schema_version`: integer, starts at `1`
- `updated_at`: ISO-8601 timestamp
- `sessions`: map[`session_id`, `AgentSession`]
- `leases`: map[`lease_id`, `CoordinationLease`]
- `handoffs`: map[`handoff_id`, `HandoffNote`]

Validation:
- `schema_version` MUST be supported by runtime.
- `updated_at` MUST be monotonic for writes within one process when possible.
- State read failure or invalid JSON maps to `DATAERR` (`65`).

## AgentSession

A caller-provided agent presence record for one `KS_ROOT`.

Fields:
- `session_id`: stable generated id
- `agent_id`: caller-provided label
- `started_at`: ISO-8601 timestamp
- `last_seen_at`: ISO-8601 timestamp
- `status`: `active | stale | closed`
- `metadata`: object, optional small key/value context

Validation:
- `agent_id` min length 1, max length 80.
- `agent_id` allows ASCII letters, digits, `.`, `_`, `-`, `@`; no slash, backslash, whitespace, or control chars.
- `last_seen_at` MUST be `>= started_at`.
- Staleness is derived from `last_seen_at + ttl`, not manually trusted.

## CoordinationLease

Temporary ownership of a work resource.

Fields:
- `lease_id`: stable generated id
- `resource_key`: caller-provided resource identifier
- `owner_agent_id`: agent label
- `owner_session_id`: session id or null
- `status`: `active | released | expired`
- `created_at`: ISO-8601 timestamp
- `renewed_at`: ISO-8601 timestamp
- `expires_at`: ISO-8601 timestamp
- `released_at`: ISO-8601 timestamp or null
- `reason`: string or null

Validation:
- `resource_key` min length 1, max length 240.
- Recommended prefixes: `source:`, `wiki:`, `graph:`, `task:`, `lease:`.
- `resource_key` MUST NOT be interpreted as a filesystem path by coordination logic.
- For one `resource_key`, at most one non-expired `active` lease may exist.
- `expires_at` MUST be later than `created_at`.

## HandoffNote

Structured handoff between agents.

Fields:
- `handoff_id`: stable generated id
- `created_by`: agent id
- `created_at`: ISO-8601 timestamp
- `resource_key`: string or null
- `summary`: string
- `next_action`: string
- `references`: list[`ResourceReference`]
- `blocked_by`: list[string]

Validation:
- `summary` and `next_action` min length 1.
- `references` may point to missing objects; missing references are lint findings, not write failures.
- `blocked_by` is human/agent-readable context, not executable dependency graph.

## ResourceReference

Weak reference to existing HKS runtime object.

Fields:
- `type`: `wiki_page | raw_source | graph_node | graph_edge | vector_chunk | lease | handoff | external`
- `value`: string
- `label`: string or null

Validation:
- `value` min length 1.
- Non-`external` references SHOULD be checked by coordination lint.
- `external` references are allowed but not validated.

## CoordinationEvent

Append-only audit entry in `coordination/events.jsonl`.

Fields:
- `event_id`: stable generated id
- `timestamp`: ISO-8601 timestamp
- `actor_agent_id`: string or null
- `action`: `session_started | heartbeat | session_closed | lease_claimed | lease_renewed | lease_released | lease_expired | handoff_added | lint_run`
- `target_type`: `session | lease | handoff | ledger`
- `target_id`: string or null
- `detail`: object

Rules:
- Every state-changing command MUST append one event.
- Event append and state update MUST occur while holding the coordination lock.

## CoordinationSummaryDetail

Payload stored in `QueryResponse.trace.steps[kind="coordination_summary"].detail`.

Fields:
- `operation`: string
- `sessions`: list[`AgentSession`], default `[]`
- `leases`: list[`CoordinationLease`], default `[]`
- `handoffs`: list[`HandoffNote`], default `[]`
- `events_appended`: integer
- `conflicts`: list[object], default `[]`
- `findings`: list[object], default `[]`

Rules:
- Success response top-level remains `QueryResponse`.
- `answer` is a short human-readable summary; machine-readable data lives in this detail object.
- Lease conflict SHOULD return `KSError.code="LEASE_CONFLICT"` and exit `1`; when possible, the error response SHOULD include a `coordination_summary` step with `conflicts[]`.
