# Requirements Checklist: Source catalog and workspace selection

**Feature**: `012-source-catalog`  
**Date**: 2026-04-26

## Content Quality

- [x] No implementation-only details leak into user stories.
- [x] User value is stated for each story.
- [x] Requirements are testable and measurable.
- [x] Non-goals are explicit: no UI, no cloud registry, no RBAC, no query-time ingest.

## Requirement Completeness

- [x] Source list and source show are independently testable.
- [x] Workspace register/list/use/query are independently testable.
- [x] Missing/corrupt manifest and registry cases are specified.
- [x] Adapter parity is specified without making CLI-only assumptions.
- [x] No-mutation boundaries are specified for catalog and registry operations.

## Constitution Alignment

- [x] Stable QueryResponse top-level shape is preserved.
- [x] New trace kind is called out as a MINOR contract extension.
- [x] No new top-level source/route enum is introduced.
- [x] Query does not trigger ingest, parsing, embedding, or refresh.
- [x] Workspace query delegates to existing query behavior.

## Readiness

- [x] Spec contains enough detail for plan/tasks.
- [x] Contracts identify expected schema additions.
- [x] Success criteria are concrete and verifiable.
- [x] Ambiguous shell environment mutation behavior is resolved.
