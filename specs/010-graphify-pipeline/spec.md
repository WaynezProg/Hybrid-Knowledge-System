# Feature Specification: Graphify pipeline

**Feature Branch**: `010-graphify-pipeline`  
**Created**: 2026-04-26  
**Status**: Complete
**Input**: User description: "009 完成，整體確認一下，使用 speckit 腳本開始做 010；/speckit.clarify /speckit.analyze 也要做。"

## Clarifications

- Q: 010 是否修改 authoritative `graph/graph.json`？ -> A: 不修改。010 產生 derived Graphify artifacts，避免把 inferred / ambiguous analysis edge 混入 ingestion graph。
- Q: 010 是否重新 ingest / re-embed source files？ -> A: 不重新做；010 只讀已存在的 wiki pages、`graph/graph.json`、manifest、008 extraction artifacts、009 wiki synthesis artifacts / applied page lineage。
- Q: 010 是否做 continuous watch / daemon？ -> A: 不做；011 才負責 watch / re-ingest / scheduled refresh。
- Q: 010 是否需要 hosted LLM？ -> A: 不需要。預設必須用 deterministic local classification / clustering；可選 hosted provider 只能沿用 008 env-gated opt-in。
- Q: 010 HTML visualization 是否等於 UI？ -> A: 不是。HTML 是 static derived artifact，不引入 server-side UI、web app、RBAC 或 cloud deployment。
- Q: 010 是否可以用 LLM 做分類？ -> A: 可以，但只用於 candidate classification / community label / audit explanation；不得讓 LLM 任意寫回 wiki、graph、vector 或 manifest。
- Q: 010 如何接 009？ -> A: 010 可以把 `origin=llm_wiki` page 和 009 candidate lineage 當成 stronger wiki evidence，但不能把未 applied candidate 視為 authoritative knowledge。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 建立 Graphify derived graph artifact（Priority: P1）

使用者或 agent 可以對既有 `KS_ROOT` 執行 Graphify build，系統讀取 wiki pages、現有 graph、manifest、008/009 lineage，產生 schema-valid derived graph artifact，包含 nodes、edges、confidence class、confidence score、provenance、run metadata 與 summary。

**Why this priority**: 010 的核心價值是把 HKS 既有三層知識升級成可分析 graph，不先有穩定 artifact 就不應做 visualization 或 report。

**Independent Test**: 用 fixture ingest + 008 store + 009 apply 建立 `KS_ROOT`，執行 Graphify preview/build。驗證 response 符合 HKS top-level contract，`graphify_summary` detail 通過 schema，且 preview 不改 `wiki/`、`graph/graph.json`、`vector/db/`、`manifest.json`。

**Acceptance Scenarios**:

1. **Given** 已初始化且至少有 wiki 或 graph data 的 `KS_ROOT`，**When** caller 執行 graphify preview，**Then** response 回傳 node/edge/community 統計、evidence source、audit summary 與 proposed output paths。
2. **Given** `graph/graph.json` 為空但 wiki pages 存在，**When** caller 執行 preview，**Then** 系統仍可從 wiki page metadata / links / headings 建立 derived nodes 並標示 evidence source。
3. **Given** `KS_ROOT` 尚未初始化或沒有可分析資料，**When** caller 執行 preview，**Then** command 以 `66` 回傳 parseable JSON，不建立 artifact。

---

### User Story 2 - 儲存 community clustering 與 JSON export（Priority: P1）

使用者或 agent 可以把 Graphify 結果存到 `$KS_ROOT/graphify/runs/<run-id>/`，產生 deterministic JSON artifacts，包含 graph、communities、audit、manifest，並更新 `$KS_ROOT/graphify/latest.json` 指向最新 run。

**Why this priority**: Graphify 必須能持久化，否則每次 agent 都要重算，也不能被 011 做增量更新。

**Independent Test**: 對同一 fixture 執行 store 兩次，驗證相同 input fingerprint 會 reuse run artifact；`graphify/latest.json` 指向同一 run；authoritative wiki/graph/vector/manifest byte-for-byte 不變。

**Acceptance Scenarios**:

1. **Given** graphify preview schema-valid，**When** caller 指定 store mode，**Then** 系統寫入 `graphify.json`、`communities.json`、`audit.json`、`manifest.json` 與 `latest.json`。
2. **Given** 相同 input fingerprint、algorithm version、classification config 已有 run，**When** caller 未指定 force，**Then** 系統重用既有 run 並在 response 標示 idempotent reuse。
3. **Given** stored graphify run artifact corrupt 或 schema mismatch，**When** 執行 `ks lint`，**Then** lint finding 指出 graphify artifact invalid。

---

### User Story 3 - 產生 HTML visualization 與 audit report（Priority: P2）

使用者或 agent 可以在 store mode 產生 static `graph.html` 與 `GRAPH_REPORT.md`，用於檢視 communities、high-confidence / ambiguous edges、跨文件關聯和 provenance。

**Why this priority**: Graphify 不只是資料結構；可讀 visualization 和 audit report 才能讓使用者判斷 LLM / inferred graph 是否可信。

**Independent Test**: 執行 store mode，驗證 HTML / Markdown artifact 存在、不含 remote script dependency、不含 absolute local secret path，report 包含 communities、top edges、ambiguous findings、input summary。

**Acceptance Scenarios**:

1. **Given** graphify run 已建立，**When** output includes HTML，**Then** 產生 self-contained static HTML，能從 local file 開啟並呈現 nodes / edges / communities。
2. **Given** graphify run 包含 `INFERRED` 或 `AMBIGUOUS` edges，**When** 產生 report，**Then** report 明確區分 evidence class 與 confidence score。
3. **Given** caller 指定 `--no-html`，**When** store mode 執行，**Then** 系統只寫 JSON / report artifacts，不寫 HTML。

---

### User Story 4 - Agent 透過 CLI / MCP / HTTP 使用同一能力（Priority: P2）

Codex、Claude、OpenClaw 或其他 agent 可以透過 CLI、MCP 或 loopback HTTP 執行 Graphify preview/store，三種入口共用 schema、error mapping、source semantics 與 local-first safety boundary。

**Why this priority**: HKS 已把 MCP / HTTP 當正式 agent surface；010 若只做 CLI，會重演 adapter drift。

**Independent Test**: 對同一 fixture 透過 CLI、MCP、HTTP 執行 preview，驗證 `graphify_summary` detail 語意等價；hosted provider 未 opt-in 時三種入口都回同類錯誤。

**Acceptance Scenarios**:

1. **Given** agent client 透過 MCP 呼叫 Graphify preview，**When** `KS_ROOT` valid，**Then** MCP success payload 與 CLI 共用同一 detail schema。
2. **Given** HTTP facade 使用 loopback host，**When** POST `/graphify/build`，**Then** success payload 是 HKS top-level response，不包 adapter-specific success envelope。
3. **Given** hosted classification provider 未通過 env opt-in，**When** caller 指定 hosted provider，**Then** command 回 `2`，不寫任何 graphify artifact。

### Edge Cases

- `KS_ROOT` 尚未初始化。
- `wiki/` 存在但 `graph/graph.json` 缺失或 schema invalid。
- `origin=llm_wiki` page 缺少 009 provenance frontmatter。
- 008 extraction artifact / 009 candidate artifact corrupt；010 必須 report audit finding，不得把壞 artifact 視為 evidence。
- 同一 `KS_ROOT` 被多個 agent 同時執行 store；late writer 必須等待 lock，lock 釋放後若 idempotency key 已命中則 reuse 既有 run 並回 `idempotent_reuse=true`，不得產生 partial run。
- HTML generation 中斷，JSON 已寫但 report/latest 未更新；implementation 必須 atomic run-dir finalize 或 lint-detectable partial state。
- LLM classification output 要求修改 wiki/graph/vector/manifest 或執行外部 side effect。
- graphify output 過大，HTML 應可關閉且 JSON/report 仍可產生。
- source path 或 report 不得洩漏使用者 home absolute path，除非該 path 已存在於 HKS artifact contract。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a Graphify build capability over existing HKS runtime data.
- **FR-002**: System MUST expose CLI entry point `ks graphify build`; this is a new namespace for derived graph analysis and MUST NOT replace `ks query` or `ks ingest`.
- **FR-003**: Default mode MUST be `preview` and MUST NOT mutate `wiki/`, `graph/graph.json`, `vector/db/`, `manifest.json`, `raw_sources/`, coordination ledger, 008 artifacts, or 009 artifacts.
- **FR-004**: System MUST support `store` mode that writes derived artifacts under `$KS_ROOT/graphify/runs/<run-id>/` and updates `$KS_ROOT/graphify/latest.json` atomically.
- **FR-005**: Graphify artifacts MUST include graph JSON, community JSON, audit JSON, run manifest, and optionally static HTML plus Markdown report.
- **FR-006**: 010 MUST NOT apply results back into authoritative graph/vector/wiki/manifest; any future apply behavior requires a separate spec.
- **FR-007**: Successful responses MUST preserve HKS top-level JSON shape and add `trace.steps[kind="graphify_summary"]` as a versioned MINOR trace detail extension.
- **FR-008**: Successful responses MUST set `trace.route="graph"`; `source` MUST contain only stable HKS source enum values actually read, typically `["wiki","graph"]` and never `"graphify"`.
- **FR-009**: Graphify edges MUST classify evidence as `EXTRACTED`, `INFERRED`, or `AMBIGUOUS` and include `confidence_score`.
- **FR-010**: Nodes, edges, communities, and audit findings MUST retain provenance to source layer and artifact where available.
- **FR-011**: Community labels MAY use LLM-assisted classification, but deterministic local classification MUST be the default and tests MUST NOT require network/API keys.
- **FR-012**: Hosted/network provider access MUST inherit 008 env-gated opt-in through `HKS_LLM_NETWORK_OPT_IN` and `HKS_LLM_PROVIDER_<ID>_API_KEY`; 010 MUST NOT introduce parallel `HKS_GRAPHIFY_NETWORK_*` gates.
- **FR-013**: Store mode MUST be idempotent by input fingerprint, algorithm version, classification config, output options, and schema version unless caller explicitly requests a new run; concurrent late writers MUST reuse an existing matching run after lock release and set `idempotent_reuse=true`.
- **FR-014**: `ks lint` MUST detect corrupt or schema-invalid graphify run artifacts, partial graphify runs, and graphify latest pointer mismatch.
- **FR-015**: MCP and HTTP adapters MUST expose the same capability if CLI is implemented; success payloads MUST NOT introduce adapter-specific envelopes.
- **FR-016**: HTML visualization MUST be static local output and MUST NOT require remote scripts, cloud service, server process, UI framework, or internet access.
- **FR-017**: Graphify report MUST clearly separate extracted evidence from inferred/ambiguous relations and include audit counts.
- **FR-018**: Error mapping MUST use existing HKS exit codes.

  | Trigger | Exit code |
  |---|---|
  | Success | `0` |
  | Usage/config error, including hosted provider without opt-in | `2` |
  | Invalid graph/wiki/graphify artifact or schema mismatch | `65` |
  | Missing runtime or no analyzable input | `66` |
  | Lock conflict or uncategorized runtime failure | `1` |
- **FR-019**: 010 MUST NOT implement continuous watch, scheduled refresh, daemon behavior, raw-source ingest, vector re-embedding, UI, RBAC, cloud sync, or microservice deployment.
- **FR-020**: Model side-effect text MUST be ignored and recorded as a finding with the existing code `side_effect_text_ignored`; it MUST NOT trigger writes outside graphify derived artifacts in explicit store mode.
- **FR-021**: Successful Graphify responses MUST set top-level `confidence=1.0` and `graphify_summary.confidence=1.0` when the run is valid; error or invalid-artifact responses MUST use `confidence=0.0`.

### Key Entities *(include if feature involves data)*

- **GraphifyRequest**: Request to build graphify output from current `KS_ROOT`, including mode, provider, algorithm version, output options, force flag, and requested_by.
- **GraphifyRun**: Stored run metadata under `$KS_ROOT/graphify/runs/<run-id>/`, including schema version, input fingerprint, created_at, artifact paths, and idempotency key.
- **GraphifyNode**: Derived node representing a source, wiki page, entity, concept, community member, or artifact-backed item.
- **GraphifyEdge**: Derived edge with relation, evidence class, confidence score, source layer, provenance, and optional rationale.
- **GraphifyCommunity**: Cluster of nodes with label, summary, member ids, representative edges, and classification provenance.
- **GraphifyAuditFinding**: Finding that explains weak evidence, ambiguity, corrupt upstream artifact, skipped input, or safety decision.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Preview responses for fixture `KS_ROOT` pass canonical HKS response schema and 010 `graphify_summary` schema 100% of the time.
- **SC-002**: Preview mode leaves `wiki/`, `graph/graph.json`, `vector/db/`, `manifest.json`, 008 artifacts, and 009 artifacts byte-for-byte unchanged.
- **SC-003**: Store mode creates one valid graphify run per idempotency key and updates `latest.json` atomically.
- **SC-004**: Stored JSON artifacts validate against contract schemas and include at least one provenance-backed node for fixture data.
- **SC-005**: HTML/report generation can be disabled; JSON/audit artifacts still complete.
- **SC-006**: Missing runtime, no analyzable input, invalid graph, partial run, hosted-provider-without-opt-in, and corrupt graphify artifact return parseable JSON with expected exit/error code.
- **SC-007**: CLI, MCP, and HTTP preview responses for the same fixture expose equivalent `graphify_summary` detail fields.

## Assumptions

- 009 is implemented and merged; 010 can treat applied `origin=llm_wiki` pages as authoritative wiki evidence.
- 008/009 stored artifacts are optional evidence; corrupt optional artifacts become audit findings rather than hard failures unless caller explicitly targets them.
- Existing `graph/graph.json` remains the ingestion graph; Graphify output is a derived analysis layer under `$KS_ROOT/graphify/`.
- 010 may add a deterministic clustering algorithm without adding a heavyweight graph database dependency.
- 011 will orchestrate repeated runs and watch/re-ingest; 010 only builds one run on demand.
