# Feature Specification: Continuous update / watch workflow

**Feature Branch**: `011-continuous-watch`  
**Created**: 2026-04-26  
**Status**: Complete
**Input**: User description: "Add 011 continuous update and watch workflow for HKS. The feature adds a local-first CLI-first watch/re-ingest orchestration layer that detects changed source inputs, schedules deterministic refresh jobs, reuses existing ingest, LLM extraction, wiki synthesis, and graphify build capabilities, records auditable refresh state, exposes adapter-compatible status/trigger controls, preserves stable HKS output contracts, avoids UI/cloud/multi-user scope, and does not silently mutate authoritative layers without explicit configured mode."

## Clarifications

### Session 2026-04-26

- Q: 011 是否需要先實作常駐背景 daemon？ -> A: 不先做常駐 daemon；MVP 以 bounded scan/run/status workflow 交付，避免新增 process lifecycle 與平台監控債。
- Q: 011 是否可以自動套用 009 wiki apply 或其他 authoritative mutation？ -> A: 預設只產生 refresh plan；只有 caller 明確指定 profile/mode 時才可觸發既有 mutation command。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 掃描變更並產生 refresh plan (Priority: P1)

使用者或 agent 可以對既有 `KS_ROOT` 與明確提供的 source roots 執行 watch scan，系統比對 source roots、manifest、parser fingerprint 與既有 derived artifacts，輸出哪些 sources 需要 re-ingest、哪些 008/009/010 artifacts 需要 refresh，以及哪些項目可安全跳過。

**Why this priority**: 沒有可審計的變更判斷，就不能安全啟動自動 refresh。P1 先交付 read-only 判斷能力，避免污染知識庫。

**Independent Test**: 建立含已 ingest source 的 fixture `KS_ROOT`，修改同一 source root 內其中一個 source，帶入該 source root 執行 watch scan 後應回傳 deterministic refresh plan，且不改 `wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json` 或 `$KS_ROOT/graphify/`。

**Acceptance Scenarios**:

1. **Given** source content changed but manifest still points to old sha256, **When** caller runs watch scan, **Then** response lists the source as `stale` and includes planned `ingest` action.
2. **Given** source content and parser fingerprint are unchanged, **When** caller runs watch scan, **Then** response lists the source as `unchanged` and no refresh action is planned.
3. **Given** a stored 008 extraction or 009 wiki candidate depends on a stale source, **When** caller runs watch scan, **Then** response marks the derived artifact lineage as stale without rewriting it.

---

### User Story 2 - 明確觸發 bounded refresh run (Priority: P1)

使用者或 agent 可以對 refresh plan 執行 bounded run。系統依序呼叫既有 ingest、optional 008 extraction、optional 009 wiki synthesis、optional 010 graphify build，並在每個 step 記錄狀態、輸入、輸出與錯誤。

**Why this priority**: watch workflow 的核心價值是把「變更偵測」接到「可重跑的現有 pipeline」，但必須保留 caller-explicit mutation 邊界。

**Independent Test**: 用 fixture 建立 stale source，執行 bounded run，確認 ingest 被更新、refresh state 記錄成功，失敗時不會留下半套 watch state。

**Acceptance Scenarios**:

1. **Given** plan contains one stale source, **When** caller runs refresh with ingest-only profile, **Then** source is re-ingested and run summary records completed ingest action.
2. **Given** caller enables graphify refresh profile, **When** run completes ingest successfully, **Then** graphify store is triggered after authoritative ingest update and run summary links to stored graphify artifacts.
3. **Given** one action fails, **When** run stops, **Then** response includes failed action, exit semantics, and enough state for a later retry without rerunning completed idempotent actions.

---

### User Story 3 - 查看 watch 狀態與歷史 (Priority: P2)

使用者或 agent 可以查看 latest watch plan、latest run、source refresh status、action history 與 blocked failures，用來判斷下一次 refresh 是否安全。

**Why this priority**: Continuous workflow 若不可觀測，agent 只能重跑或猜測狀態，會造成重複寫入與難以追蹤的資料污染。

**Independent Test**: 執行一次 scan 與一次 bounded run 後，status command 能以同一 response contract 回傳 latest plan/run、counts、blocked failures 與 artifact references。

**Acceptance Scenarios**:

1. **Given** watch run has completed, **When** caller requests status, **Then** response includes latest run id, completed/failed counts, and affected source relpaths.
2. **Given** previous run failed, **When** caller requests status, **Then** response exposes blocked action and retry hint without hiding partial completion.

---

### User Story 4 - 透過 MCP / HTTP 觸發同一 watch 能力 (Priority: P2)

Agent 可以透過 local MCP tool 或 loopback HTTP endpoint 呼叫 watch scan、run、status，語意與 CLI 一致，錯誤 envelope 仍符合既有 adapter contract。

**Why this priority**: HKS 已把 CLI/MCP/HTTP 視為正式介面；011 若只做 CLI 會造成 agent surface drift。

**Independent Test**: 對同一 fixture 分別呼叫 CLI、MCP、HTTP scan/status，確認 response top-level shape、trace kind、counts 與 error mapping 一致。

**Acceptance Scenarios**:

1. **Given** caller invokes MCP watch scan with valid `ks_root`, **When** scan succeeds, **Then** response matches CLI scan semantics.
2. **Given** caller invokes HTTP watch run from non-loopback host without explicit opt-in, **When** server validates host binding, **Then** request is rejected by existing loopback safety behavior.

### Edge Cases

- Source file is deleted after previous ingest: scan marks it as `missing` and plans prune only when caller explicitly enables prune behavior.
- Source file changes while a bounded run is executing: run records the observed fingerprint and reports if final fingerprint no longer matches.
- Corrupt or unsupported source appears under watched roots: scan reports it as an actionable issue but does not crash the whole plan.
- Existing 008/009/010 artifact references a source no longer present in manifest: scan marks lineage as orphaned and leaves remediation to explicit run profile.
- Two agents trigger watch run concurrently: only one run may hold the watch lock; the loser receives a deterministic conflict error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a watch scan capability that reads existing HKS runtime state plus explicit source roots or saved watch config and returns a refresh plan without mutating authoritative layers.
- **FR-002**: System MUST classify source state at minimum as `unchanged`, `stale`, `new`, `missing`, `unsupported`, or `corrupt`.
- **FR-003**: System MUST treat content sha256, source format, parser fingerprint, source relpath, and lineage references as refresh decision inputs.
- **FR-004**: System MUST NOT pretend to detect external source changes when neither source roots nor saved watch config are available; it must report a usage error or scan only `$KS_ROOT/raw_sources` as an internal consistency source.
- **FR-005**: System MUST identify stale 008 extraction, 009 wiki synthesis, and 010 graphify artifacts when their source lineage or upstream artifacts changed.
- **FR-006**: System MUST provide a bounded watch run capability that executes a caller-approved refresh plan using existing HKS command behavior.
- **FR-007**: System MUST keep authoritative mutations caller-explicit; default scan and default run profile MUST NOT silently apply wiki synthesis or graphify store.
- **FR-008**: System MUST persist watch plans, run summaries, action state, timestamps, input fingerprints, output references, and errors under a derived watch state area.
- **FR-009**: System MUST expose latest status and run history sufficient for retry, audit, and agent handoff.
- **FR-010**: System MUST use the existing top-level HKS success response shape and add a watch trace detail kind without introducing a new top-level `source` enum.
- **FR-011**: System MUST expose watch scan/run/status through CLI and adapter-compatible MCP/HTTP surfaces.
- **FR-012**: System MUST serialize bounded watch runs with a dedicated watch lock and return deterministic conflict errors for concurrent runs.
- **FR-013**: System MUST support dry-run and explicit execution modes so users can inspect planned changes before refresh.
- **FR-014**: System MUST include lint coverage for corrupt watch state, partial runs, stale latest pointers, and invalid watch artifacts.
- **FR-015**: System MUST update README, README.en.md, docs/main.md, docs/PRD.md, contracts, and quickstart when the public surface is implemented.

### Key Entities *(include if feature involves data)*

- **Watch Source**: A source relpath plus observed filesystem state, content fingerprint, parser fingerprint, previous manifest state, and issue classification.
- **Watch Root**: A caller-provided or saved filesystem root whose relative paths are compared against manifest source relpaths.
- **Refresh Plan**: A deterministic list of actions needed to reconcile watched sources and derived artifacts.
- **Refresh Action**: One executable unit such as ingest, prune, llm classify, wiki synthesize, wiki apply, graphify build, or status-only remediation.
- **Watch Run**: A bounded execution attempt with run id, plan fingerprint, requested profile, action results, timestamps, and final status.
- **Watch State**: Persisted latest pointers, run summaries, event log, and validation metadata under `$KS_ROOT/watch/`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Watch scan over 100 manifest entries completes in under 3 seconds on local fixtures and performs zero authoritative writes.
- **SC-002**: Re-running scan on unchanged inputs returns an identical plan fingerprint and zero planned refresh actions.
- **SC-003**: A bounded ingest-only run updates exactly the stale source entries identified by the plan and records completed action state.
- **SC-004**: Failed action responses include run id, action id, error code, exit code, and retry hint.
- **SC-005**: CLI, MCP, and HTTP scan/status responses agree on source counts, run ids, and trace step kind for the same `KS_ROOT`.
- **SC-006**: Lint detects corrupt watch artifacts and partial watch runs with deterministic finding categories.

## Assumptions

- 011 targets local personal knowledge roots, not cloud sync, team RBAC, or multi-user scheduling.
- MVP uses bounded commands; always-on daemon and OS-specific filesystem watcher integration are out of scope unless added by a later explicit story.
- Existing ingest, 008 extraction, 009 wiki synthesis, 010 graphify, lint, MCP, and HTTP adapter primitives are reused instead of reimplementing pipelines.
- Existing manifest entries do not retain the original external source root, so external change detection requires caller-provided `source_roots` or a saved watch config.
- Network/hosted provider opt-in rules from 008/009/010 remain unchanged.
- Watch artifacts are derived operational state and must not be treated as authoritative wiki, graph, vector, or manifest content.
