# Requirements Checklist: Phase 3 階段三 — MCP / API adapter

**Purpose**: 驗證 006 spec / plan 在 implementation 前是否足夠清楚、完整、一致。
**Created**: 2026-04-26
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Are all MVP tools explicitly named and scoped? [Completeness, Spec §Requirements FR-001]
- [x] CHK002 Are query, ingest, and lint inputs specified with defaults? [Completeness, Spec §FR-003/004/005]
- [x] CHK003 Are success and error output contracts both defined? [Completeness, Data Model Successful Tool Payload/AdapterError]
- [x] CHK004 Is HTTP REST clearly marked as optional P2 rather than MVP? [Scope, Spec US3, Plan Summary]

## Requirement Clarity

- [x] CHK005 Is the adapter success payload required to remain the existing HKS QueryResponse shape? [Clarity, Spec FR-002]
- [x] CHK006 Is the adapter query write-back default explicitly different from CLI and justified? [Clarity, Edge Cases write-back]
- [x] CHK007 Are local-only binding expectations measurable for Streamable HTTP / REST? [Clarity, Spec US3]

## Requirement Consistency

- [x] CHK008 Do spec, plan, data model, and contracts use the same tool names? [Consistency]
- [x] CHK009 Do adapter error exit code values align with constitution §II? [Consistency, Constitution §II]
- [x] CHK010 Does 006 avoid changing `source` / `trace.route` enum values? [Consistency, Spec FR-002]

## Scenario Coverage

- [x] CHK011 Are primary MCP query and MCP ingest/lint flows independently testable? [Coverage, Spec US1/US2]
- [x] CHK012 Are uninitialized runtime, lock contention, usage error, and no-network cases specified? [Coverage, Edge Cases, SC-003/004]
- [x] CHK013 Is optional HTTP behavior covered without blocking MCP MVP? [Coverage, Spec US3]

## Non-Functional Requirements

- [x] CHK014 Are local-first and airgapped constraints explicitly specified? [NFR, Spec FR-010]
- [x] CHK015 Are performance expectations measurable enough for implementation tasks? [NFR, Plan Technical Context]
- [x] CHK016 Are security boundaries stated without introducing out-of-scope RBAC/auth? [NFR, Research auth decision]
