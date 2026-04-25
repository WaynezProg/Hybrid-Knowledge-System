# Feature Specification: Phase 3 階段三 — Multi-agent support

**Feature Branch**: `007-multi-agent-support`
**Created**: 2026-04-26
**Status**: Complete
**Input**: Phase 3 remaining scope: add local multi-agent coordination support on top of the existing HKS CLI/MCP adapter without adding UI, cloud, RBAC, or hosted orchestration.

## Clarifications

- Q: 007 的「multi-agent」是否包含 agent scheduler / supervisor？ → A: 不包含；007 只做本機 coordination primitives：session、lease、handoff、status。
- Q: CLI namespace 應該叫 `agent` 還是 `coord`？ → A: 使用 `ks coord ...`；這避免把 HKS 誤導成會啟動或管理 agent process。
- Q: Coordination ledger 是否是 authentication / authorization？ → A: 不是；`agent_id` 僅是 caller-provided local label，不授權、不隔離、不防冒用。
- Q: HTTP facade 是否阻塞 MVP？ → A: 不阻塞；MVP 是 CLI + MCP coordination tools，HTTP facade 保持 P3 optional。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent 宣告工作身份與心跳（Priority: P1）

多個本機 agent 共用同一個 `KS_ROOT` 時，每個 agent 可以用明確 `agent_id` 建立 session、更新 heartbeat、查詢目前活躍 session，讓使用者和其他 agent 知道誰正在操作同一份 knowledge base。

**Why this priority**：沒有身份與活躍狀態，多 agent 只是在同一個目錄裡互相覆蓋；後續 claim / handoff 都無法可靠歸屬。

**Independent Test**：用兩個不同 `agent_id` 在同一個暫存 `KS_ROOT` 建立 session，再查 status，驗證兩者都出現在 schema-valid response，且 stale session 可由 TTL 判定。

**Acceptance Scenarios**：

1. **Given** 已初始化的 `KS_ROOT`，**When** agent A 呼叫 session start，**Then** response 顯示 agent A active，並寫入 coordination ledger。
2. **Given** agent A 已 start，**When** agent A 更新 heartbeat，**Then** session `last_seen_at` 更新且不新增重複 session。
3. **Given** agent A 超過 TTL 未 heartbeat，**When** agent B 查 status，**Then** agent A 標示 stale，而非 active。

---

### User Story 2 — Agent 對工作資源取得 lease（Priority: P1）

agent 可以對一個 resource key 取得限時 lease，例如 `source:docs/foo.md`、`task:reingest-project-atlas`、`wiki:project-atlas`。同一時間只允許一個 active lease，避免多 agent 重複 ingest、重複 fix 或同時改同一份 wiki 相關工作。

**Why this priority**：HKS 已有單流程 file lock，但那只保護瞬間寫入；多 agent 需要較長生命週期的「誰負責什麼」協調。

**Independent Test**：agent A claim 同一 resource 後，agent B claim 應回 conflict；agent A release 或 lease 過期後，agent B 可成功 claim。

**Acceptance Scenarios**：

1. **Given** resource 尚未被 claim，**When** agent A claim，**Then** 回傳 active lease id、owner、expires_at。
2. **Given** agent A 持有未過期 lease，**When** agent B claim 同一 resource，**Then** 回傳 structured conflict，且不覆蓋 agent A lease。
3. **Given** agent A lease 已過期，**When** agent B claim 同一 resource，**Then** agent B 成為新的 owner，舊 lease 標示 expired。

---

### User Story 3 — Agent 留下 handoff note（Priority: P2）

agent 可以留下結構化 handoff note，包含 summary、next_action、references、blocked_by，讓下一個 agent 能從 HKS 本機 coordination ledger 讀取交接狀態，不需要解析自然語言聊天紀錄。

**Why this priority**：多 agent 協作的核心不是同時執行，而是能穩定交接上下文；handoff note 是最小可用協作單位。

**Independent Test**：agent A 建立 handoff note 後，agent B 查詢 handoff list，能依 resource / agent / time range 取得 note，且 note references 指向已存在或明確標示 missing。

**Acceptance Scenarios**：

1. **Given** agent A 已完成一段查詢與 lint，**When** agent A 建立 handoff note，**Then** note 寫入 ledger 並可被 agent B 查到。
2. **Given** handoff note references 一個不存在的 wiki page，**When** 執行 coordination lint，**Then** finding 標示 missing reference。

---

### User Story 4 — MCP / HTTP adapter 暴露相同 coordination 能力（Priority: P2）

外部 agent 不必 shell out；可透過 006 已完成的 MCP / HTTP adapter 使用 session、lease、handoff 能力，且成功與錯誤契約和 CLI 對齊。

**Why this priority**：006 已是 agent-facing 入口；007 若只做 CLI，會迫使 MCP client 回到 shell wrapping。

**Independent Test**：用 in-process MCP server 呼叫 coordination tools，與 CLI 對同一 `KS_ROOT` 的結果一致；HTTP facade 若納入，endpoint 只綁 loopback。

**Acceptance Scenarios**：

1. **Given** agent A 透過 MCP claim resource，**When** agent B 透過 CLI 查 status，**Then** 兩邊看到同一 lease。
2. **Given** non-loopback HTTP host，**When** 啟動 coordination HTTP endpoint，**Then** 預設拒絕，沿用 006 local-first 安全邊界。

### Edge Cases

- `agent_id` 為空、過長、含 path separator 或控制字元。
- `resource_key` 為空、過長、或試圖 encode 任意本機 path traversal。
- 同一 `KS_ROOT` 內兩個 process 同時 claim 同一 resource。
- agent crash 後 lease 未 release，但 TTL 到期。
- 系統時間回撥導致 `expires_at` 早於 `created_at`。
- handoff reference 指向不存在的 wiki page、raw source、graph node 或 lease id。
- coordination ledger 壞檔或部分寫入。
- `KS_ROOT` 尚未初始化時呼叫 coordination command。
- 多 agent coordination 不得繞過既有 ingest / lint file lock。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**：系統 MUST 提供本機 multi-agent coordination 能力，最小集合包含 session、lease、handoff、status。
- **FR-002**：所有 coordination command 成功 output MUST 維持 HKS top-level `QueryResponse` shape；若新增 `trace.steps.kind`，MUST 更新 canonical schema，並視為 §II MINOR 擴充。
- **FR-003**：coordination 錯誤 MUST 沿用現有 exit code 語意：usage 錯誤為 `2`、未初始化 `KS_ROOT` 為 `66`、ledger 壞檔為 `65`、lease conflict / lock / runtime failure 為 `1`；lease conflict 的 `KSError.code` MUST be `LEASE_CONFLICT`。
- **FR-004**：系統 MUST 提供 `ks coord` CLI namespace；不得以 `ks agent` 命名，避免暗示 HKS 會啟動或控制 agent。
- **FR-005**：系統 MUST 支援 caller-provided `agent_id`；`agent_id` 只是本機協作標籤，不得被描述為 authentication 或 authorization。
- **FR-006**：`ks coord session start|heartbeat|close` MUST 支援 session 建立、心跳更新與關閉。
- **FR-007**：`ks coord status` MUST 支援 session / lease / handoff 狀態查詢。
- **FR-008**：`ks coord lease claim|renew|release` MUST 支援 resource lease 生命週期。
- **FR-009**：`ks coord handoff add|list` MUST 支援 handoff note 寫入與查詢。
- **FR-010**：session MUST 記錄 `agent_id`、`session_id`、`started_at`、`last_seen_at`、`status`。
- **FR-011**：lease MUST 支援 `claim`、`renew`、`release`、`expire` 語意，且同一 `resource_key` 同時只能有一個 active lease。
- **FR-012**：lease claim MUST 是 atomic；並行 claim 同一 resource 不得產生兩個 active owner。
- **FR-013**：handoff note MUST 支援 `summary`、`next_action`、`references`、`blocked_by`、`created_by`、`created_at`。
- **FR-014**：coordination ledger MUST 位於 `KS_ROOT/coordination/`，不得寫入 repo 根目錄或使用者 home 目錄作為 runtime state。
- **FR-015**：coordination ledger MUST 可被 `ks lint` 或 `ks coord lint` 檢查壞檔、stale lease、missing reference。
- **FR-016**：MCP adapter MUST 暴露 coordination tools；成功 payload 不得引入 adapter-specific success envelope。
- **FR-017**：HTTP facade 若納入 007，MUST 沿用 006 loopback-only default。
- **FR-018**：007 MUST NOT 實作 agent scheduler、agent process launcher、LLM supervisor、task planner、RBAC、cloud sync、UI 或 microservice deployment。
- **FR-019**：007 MUST NOT 改變 `ks ingest`、`ks query`、`ks lint` 既有語意；coordination 是協作輔助層，不是 query routing 或 ingestion replacement。
- **FR-020**：write-back safety MUST 保持：agent read path 預設不得默默寫入 wiki；handoff 寫入的是 coordination ledger，不等同 knowledge write-back。
- **FR-021**：所有 coordination writes MUST append an operational event，可供 audit 與 replay。
- **FR-022**：coordination responses MUST include a `trace.steps[kind="coordination_summary"]` detail payload whose schema is versioned under `specs/007-multi-agent-support/contracts/`。

### Key Entities

- **AgentSession**：一個本機 agent 在特定 `KS_ROOT` 的活動宣告；不是帳號，也不是權限主體。
- **CoordinationLease**：某 agent 對某 resource key 的限時 ownership；用於避免重複工作與衝突。
- **HandoffNote**：agent 交接紀錄，包含下一步、阻塞點與可追溯 references。
- **ResourceReference**：指向 HKS 既有 runtime object 的弱引用，例如 wiki page、raw source relpath、graph node id、lease id。
- **CoordinationLedger**：`KS_ROOT` 內的本機協作狀態與事件紀錄。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：兩個 agent 同時 claim 同一 resource 的 100 次 regression test 中，active owner 永遠只有一個。
- **SC-002**：session start / heartbeat / status / claim / release / handoff 的成功 response 100% 通過 canonical HKS response schema。
- **SC-003**：未初始化 `KS_ROOT`、invalid `agent_id`、lease conflict、ledger 壞檔四類錯誤 100% 回傳可解析 JSON 與預期 exit/error code。
- **SC-004**：stale lease cleanup 或 expiry 判定可在 fixture 尺度下 1 秒內完成。
- **SC-005**：MCP coordination tools 與 CLI 對同一 fixture runtime 的 session / lease / handoff 狀態一致。
- **SC-006**：coordination ledger 壞檔不會破壞既有 `ks query` 對 wiki / graph / vector 的 read path。

## Assumptions

- 007 的目標是讓多個本機 agent 能共享 HKS runtime 時不互相踩踏；不是替 agent 分派任務或執行任務。
- 所有 agent 都在同一台本機或同一個可信本機檔案系統上操作同一 `KS_ROOT`。
- `agent_id` 由 caller 提供；HKS 不負責驗證真實身份。
- 006 MCP / HTTP adapter 已在 main，007 可重用其 adapter core 與 local-first safety defaults。
- Coordination state 可以是新增 runtime layout；但不得改變既有 `raw_sources/`、`wiki/`、`graph/`、`vector/`、`manifest.json` 的語意。
