# Feature Specification: LLM-assisted wiki synthesis

**Feature Branch**: `009-llm-wiki-synthesis`  
**Created**: 2026-04-26  
**Status**: Draft  
**Input**: User description: "現在可以開始 009，觀察目前專案狀態，做最好的 Speckit；一樣做到 implementation 前。"

## Clarifications

- Q: 009 是否要重新做 008 的 LLM classification / extraction？ -> A: 不重做；009 consume 008 stored extraction artifact。若沒有 matching artifact，回報可解析錯誤並提示先跑 `ks llm classify --mode store`。
- Q: 009 是否要做 Graphify community clustering、HTML visualization 或 audit report？ -> A: 不包含；010 負責 Graphify。
- Q: 009 是否要做資料夾 watch / daemon 式持續更新？ -> A: 不包含；011 負責 continuous update / watch workflow。
- Q: 009 是否可以自動寫 wiki？ -> A: 不行；預設 `preview` read-only，只有 caller 明確指定 `apply` 才能修改 `wiki/`。
- Q: 009 apply 是否同步更新 graph / vector？ -> A: 不同步；009 只修改 wiki layer 並留下 provenance / log。Graphify 與跨層持續更新留給 010/011。
- Q: hosted LLM 是否必要？ -> A: 不必要；009 必須可用 deterministic fake synthesizer 離線測試，hosted/network provider 延續 008 env-gated opt-in 規則。
- Q: 009 apply 是否可以重新產生 candidate？ -> A: 不行；`apply` 必須使用已由 `store` 產生的 `candidate_artifact_id`，缺少 stored candidate 時回 `66`。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 預覽 wiki page candidate（Priority: P1）

使用者或 agent 可以從 008 stored extraction artifact 產生 wiki page candidate，看到 title、summary、body、provenance、related source、target slug 與 proposed diff，但不寫入 `wiki/`、`graph/`、`vector/` 或 `manifest.json`。

**Why this priority**: 這是 LLM Wiki 的最小可用能力；沒有 preview，就只能讓 LLM 直接寫入知識庫，會破壞 write-back safety。

**Independent Test**: 建立 fixture `KS_ROOT`，先用 008 fake provider 產生 stored extraction artifact，再執行 009 preview。驗證 response 符合 HKS top-level contract，`trace.steps[kind="wiki_synthesis_summary"]` detail 通過 schema，且 runtime knowledge layers byte-for-byte 不變。

**Acceptance Scenarios**:

1. **Given** 已存在 valid 008 extraction artifact，**When** caller 執行 wiki synthesis preview，**Then** response 回傳 wiki page candidate、target slug、diff summary、source fingerprint 與 artifact provenance。
2. **Given** 找不到 matching 008 artifact，**When** caller 執行 preview，**Then** command 以 `66` 回傳 parseable JSON，提示先執行 `ks llm classify <source-relpath> --mode store`。
3. **Given** 008 artifact source fingerprint 與 manifest 不一致，**When** caller 執行 preview，**Then** command 以 `65` 回報 stale artifact，不產生 candidate。

---

### User Story 2 - 儲存可審核 wiki synthesis candidate（Priority: P1）

使用者或 agent 可以把 wiki page candidate 存成 versioned candidate artifact，供稍後 apply、review、handoff 或 audit 使用；store 仍不得修改 authoritative wiki。

**Why this priority**: Wiki synthesis output 也需要可追溯、可重用；否則 apply 前後無法證明頁面內容來自哪個 extraction artifact 和 prompt version。

**Independent Test**: 對同一 extraction artifact 執行 store mode 兩次，驗證 `$KS_ROOT/llm/wiki-candidates/` 只產生一個 idempotent candidate artifact，且 wiki / graph / vector / manifest 不變。

**Acceptance Scenarios**:

1. **Given** preview candidate schema-valid，**When** caller 指定 store mode，**Then** 系統寫入 wiki synthesis candidate artifact 並在 response 回傳 candidate reference。
2. **Given** 同一 extraction artifact、prompt version、provider、model 已有 candidate artifact，**When** caller 未指定 force，**Then** 系統重用既有 candidate artifact 並標示 idempotent reuse。
3. **Given** candidate artifact partial / corrupt，**When** 執行 `ks lint`，**Then** lint finding 標示 wiki synthesis candidate artifact 壞檔或 schema mismatch。

---

### User Story 3 - 明確 apply wiki candidate（Priority: P2）

使用者或 agent 可以明確 apply 一個 stored wiki synthesis candidate artifact 到 `wiki/pages/`，系統要 rebuild `wiki/index.md`、append `wiki/log.md`，並在 response 中列出 touched page、mode、provenance、conflicts 與 diff summary。

**Why this priority**: 009 的交付不只是產生文字，而是把 approved LLM Wiki candidate 安全沉澱到 HKS wiki layer。

**Independent Test**: 用 stored candidate 執行 apply，驗證新增或更新的 wiki page frontmatter 含 `origin=llm_wiki`、source artifact reference、source fingerprint、prompt version；`wiki/index.md` 和 `wiki/log.md` 更新；graph / vector / manifest 不變。

**Acceptance Scenarios**:

1. **Given** stored wiki synthesis candidate artifact，**When** caller 以 `candidate_artifact_id` 指定 apply，**Then** 系統建立或更新 wiki page，並記錄 log entry。
2. **Given** target slug 已存在且內容不是同一 source lineage 或既有 page 不是 `origin=llm_wiki`，**When** caller 未指定 overwrite policy，**Then** response 回報 conflict，不覆蓋既有 page。
3. **Given** candidate artifact 已 stale，**When** caller 指定 apply，**Then** command 以 `65` 回報 stale candidate，不寫入 wiki。

---

### User Story 4 - Agent 透過 CLI / MCP / HTTP 使用同一能力（Priority: P2）

Codex、Claude、OpenClaw 或其他 agent 可以透過 CLI、MCP 或 loopback HTTP 執行 wiki synthesis preview/store/apply，三種入口使用同一 schema、同一 error mapping、同一 local-first safety boundary。

**Why this priority**: HKS 的正式 agent surface 已包含 CLI、MCP、HTTP；009 若只做 CLI，agent 會被迫自己包 shell，導致 contract drift。

**Independent Test**: 對同一 fixture candidate，透過 CLI、MCP、HTTP 執行 preview，驗證 `wiki_synthesis_summary` detail 語意等價；HTTP non-loopback 預設拒絕。

**Acceptance Scenarios**:

1. **Given** agent client 透過 MCP 呼叫 wiki synthesis preview，**When** artifact valid，**Then** MCP success payload 與 CLI 共用同一 detail schema。
2. **Given** HTTP facade 綁定 non-loopback host，**When** 啟動 wiki synthesis endpoint，**Then** 預設拒絕，沿用 006 safety boundary。
3. **Given** hosted provider 未通過 008 env-gated opt-in，**When** agent 要求使用 hosted provider，**Then** 回傳 `2` usage error，不寫入 artifact 或 wiki。

### Edge Cases

- `KS_ROOT` 尚未初始化。
- source relpath 存在但沒有 matching 008 extraction artifact。
- 008 extraction artifact JSON 壞檔、schema version 不支援、source fingerprint stale。
- candidate body 為空、title 為空、frontmatter invalid、slug collision。
- apply target page 已存在，但 lineage 不一致或 page origin 不是 `llm_wiki`。
- apply 過程中斷導致 wiki page 已寫但 index/log 未更新；implementation 必須用 atomic write + rollback 或 lint-detectable partial state 避免靜默污染。
- 同一 candidate 被兩個 agent 同時 apply；late writer 必須在 lock 釋放後回報 idempotent apply 或 conflict。
- LLM output 嘗試要求修改 graph / vector / manifest 或執行外部 side effect。
- hosted/network provider 被請求但缺少 env opt-in 或 credential。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide LLM-assisted wiki synthesis from valid 008 extraction artifacts.
- **FR-002**: System MUST expose a CLI entry point as `ks wiki synthesize`; `ks wiki` is a new namespace intended to host future sibling subcommands for 010/011, and implementation MAY add subcommands only if this primary entry point remains available.
- **FR-003**: Default mode MUST be `preview` and MUST NOT mutate `wiki/`, `graph/graph.json`, `vector/db/`, `manifest.json`, or 008 extraction artifacts.
- **FR-004**: System MUST support `store` mode that writes versioned wiki synthesis candidate artifacts under `$KS_ROOT/llm/wiki-candidates/` without modifying authoritative wiki pages.
- **FR-005**: System MUST support caller-explicit `apply` mode that requires a stored `candidate_artifact_id`, writes or updates wiki pages, rebuilds `wiki/index.md`, and appends `wiki/log.md`; this is not confidence-triggered automatic query write-back under Constitution §V.
- **FR-006**: `apply` mode MUST NOT mutate graph, vector, raw sources, manifest, coordination ledger, or 008 extraction artifacts.
- **FR-007**: Successful responses MUST preserve HKS top-level JSON shape and add `trace.steps[kind="wiki_synthesis_summary"]` as a versioned MINOR trace detail extension.
- **FR-008**: Successful preview/store responses MUST set `trace.route="wiki"` and `source=[]`; successful apply responses MUST set `trace.route="wiki"` and `source=["wiki"]` only after wiki write succeeds; apply conflict/error responses MUST use `source=[]` when returning an HKS top-level response.
- **FR-009**: Wiki synthesis output MUST include target slug, title, summary, body, source relpath, extraction artifact reference, source fingerprint, parser fingerprint, prompt version, provider id, model id, diff summary, confidence, and findings.
- **FR-010**: Applied wiki pages MUST use a distinguishable origin value `llm_wiki` and preserve source artifact provenance in frontmatter, including `origin`, `slug`, `generated_at`, `source_relpath`, `source_fingerprint`, `extraction_artifact_id`, `wiki_candidate_artifact_id`, `prompt_version`, `provider_id`, and `model_id`.
- **FR-011**: Existing wiki pages MUST NOT be overwritten when lineage conflicts unless caller explicitly supplies a future overwrite policy; lineage is equal only when `(extraction_artifact_id, source_fingerprint, parser_fingerprint)` all match. `prompt_version`, `provider_id`, or `model_id` differences do not create lineage conflict but MUST be recorded as an update. Any existing target page whose origin is not `llm_wiki` MUST be treated as conflict and fail closed.
- **FR-012**: Candidate artifacts MUST be created only by `store` mode and be idempotent by extraction artifact id, source fingerprint, synthesis prompt version, provider id, model id, target slug, and schema version unless caller explicitly requests a new run. `apply` MUST reuse a stored candidate artifact and MUST NOT regenerate or store a new candidate.
- **FR-013**: `ks lint` MUST detect corrupt or schema-invalid wiki synthesis candidate artifacts and invalid `origin=llm_wiki` applied-page frontmatter after 009 implementation; wiki-to-manifest reconciliation MUST skip valid `origin=llm_wiki` pages so existing 005 lint behavior is not broken.
- **FR-014**: Provider configuration MUST remain local-first and inherit 008 hosted/network provider gates through `HKS_LLM_NETWORK_OPT_IN` and `HKS_LLM_PROVIDER_<ID>_API_KEY`; 009 MUST NOT introduce parallel `HKS_WIKI_NETWORK_*` gates. Tests MUST use deterministic fake synthesizer and require no network/API keys.
- **FR-015**: MCP and HTTP adapters MUST expose the same capability if CLI is implemented; success payloads MUST NOT introduce adapter-specific envelopes.
- **FR-016**: 009 MUST NOT implement Graphify clustering/visualization/audit report, graph apply, vector apply, watch/daemon scheduling, UI, RBAC, cloud sync, or microservice deployment.
- **FR-017**: Error mapping MUST use existing HKS exit codes.

  | Trigger | Exit code |
  |---|---|
  | Success | `0` |
  | Usage/config error, including hosted provider without opt-in | `2` |
  | Stale or invalid extraction artifact / candidate artifact | `65` |
  | Missing runtime, source, extraction artifact, or candidate artifact | `66` |
  | Write conflict or uncategorized runtime failure | `1` |
- **FR-018**: All wiki synthesis writes MUST leave traceable audit evidence in response detail and `wiki/log.md`; apply writes MUST follow an atomic sequence that prevents a committed page without corresponding index/log evidence.
- **FR-019**: LLM prompts and synthesizer behavior MUST be domain-agnostic; no legal/medical/code/company-specific taxonomy may be hard-coded.
- **FR-020**: Model side-effect text MUST be ignored and recorded as a finding with the existing 008 code `side_effect_text_ignored`; it MUST NOT trigger writes outside explicit `apply` mode.

### Key Entities *(include if feature involves data)*

- **WikiSynthesisRequest**: Request to synthesize a wiki page from a source relpath, extraction artifact, or stored candidate artifact, including mode, target slug, prompt version, provider, and force flag.
- **WikiSynthesisCandidate**: Schema-validated candidate wiki page containing title, summary, body, provenance, confidence, target slug, diff summary, and findings.
- **WikiSynthesisArtifact**: Stored candidate artifact under `$KS_ROOT/llm/wiki-candidates/`, versioned by extraction artifact and synthesis lineage.
- **WikiApplyResult**: Result of applying a candidate to `wiki/pages/`, including touched pages, log entry, conflict list, and diff summary.
- **WikiLineage**: Provenance linking applied page -> synthesis candidate -> 008 extraction artifact -> raw source fingerprint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Preview responses for fixture artifacts pass canonical HKS response schema and 009 `wiki_synthesis_summary` schema 100% of the time.
- **SC-002**: Preview and store modes leave `wiki/`, `graph/graph.json`, `vector/db/`, and `manifest.json` byte-for-byte unchanged.
- **SC-003**: Store mode creates exactly one valid candidate artifact per idempotency key unless force/new-run is explicitly requested.
- **SC-004**: Apply mode writes one wiki page from a stored candidate artifact, rebuilds `wiki/index.md`, appends one `wiki/log.md` entry, supports idempotent same-lineage concurrent apply, and leaves graph/vector/manifest unchanged in regression tests.
- **SC-005**: Missing extraction artifact, missing stored candidate artifact, stale extraction artifact, stale candidate artifact, slug conflict, hosted-provider-without-opt-in, and invalid candidate artifact return parseable JSON with expected exit/error code.
- **SC-006**: CLI, MCP, and HTTP preview responses for the same fixture expose equivalent `wiki_synthesis_summary` detail fields.

## Assumptions

- 008 is already implemented and merged; 009 can rely on `$KS_ROOT/llm/extractions/*.json` as the upstream candidate source.
- Existing ingest-created wiki pages may coexist with 009 `llm_wiki` pages; conflict policy must be explicit rather than silent overwrite.
- 009 is the wiki layer step of the larger LLM Wiki + Graphify + Vector vision; 010 owns Graphify and 011 owns continuous orchestration.
- Applied wiki pages are human-readable knowledge artifacts, not replacements for raw source files.
- 009 `apply` is caller-explicit mutation, not confidence-triggered automatic query write-back under Constitution §V.
- `ks wiki` is intentionally introduced as a namespace so 010/011 can add related wiki/graphification workflow commands without overloading `ks query`.
