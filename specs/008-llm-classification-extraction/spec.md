# Feature Specification: LLM-assisted classification and extraction

**Feature Branch**: `008-llm-classification-extraction`  
**Created**: 2026-04-26  
**Status**: Complete  
**Input**: User description: "8~11 都要做；先做 008，嚴格執行 Speckit，到 implementation 前。目標是 LLM Wiki + Graphify + Vector，先建立 LLM 分類與抽取基礎。"

## Clarifications

- Q: 008 是否要完成完整 LLM Wiki rewriting？ -> A: 不包含；008 只產生 schema-validated summary / fact / entity / relation candidates，wiki synthesis 與寫回決策留給 009。
- Q: 008 是否要完成 Graphify community clustering、HTML visualization 或 audit report？ -> A: 不包含；008 只提供 Graphify 可消費的候選 entity / relation / classification artifact，Graphify pipeline 留給 010。
- Q: 008 是否要做資料夾 watch / daemon 式持續更新？ -> A: 不包含；008 是執行時 command / adapter 能力，continuous update 留給 011。
- Q: 008 是否要求 hosted LLM？ -> A: 不要求；local-first 是硬限制，network / hosted provider 只能 explicit opt-in，測試必須使用 deterministic fake provider。
- Q: 008 能否自動修改 wiki / graph / vector？ -> A: 不行；預設 preview，只能 explicit store extraction artifact；不得自動 apply 到三層知識庫。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 取得 schema-valid LLM 抽取候選（Priority: P1）

使用者或 agent 可以對已 ingest 的 source 執行 LLM-assisted classification/extraction，取得分類、摘要候選、key facts、entity candidates、relation candidates、confidence、evidence spans、provenance 與 model metadata。結果必須是穩定 JSON，且預設不改動既有 wiki / graph / vector。

**Why this priority**: 沒有穩定抽取候選，後續 009 Wiki synthesis、010 Graphify、011 continuous update 都沒有可靠輸入。

**Independent Test**: 使用 deterministic fake provider 對 fixture source 執行 `ks llm classify`，驗證 stdout 符合 HKS top-level response shape，`trace.steps[kind="llm_extraction_summary"]` detail 通過 contract schema，且 `wiki/`、`graph/graph.json`、`vector/db/` 未被修改。

**Acceptance Scenarios**:

1. **Given** 已初始化且已 ingest 的 `KS_ROOT`，**When** agent 對某個 raw source relpath 執行 LLM classification/extraction preview，**Then** response 包含分類、摘要候選、key facts、entities、relations、confidence 與 evidence。
2. **Given** fake provider 回傳 malformed JSON，**When** 系統驗證輸出，**Then** command 失敗且回傳 schema-valid error response，不寫入 extraction artifact。
3. **Given** source 已被更新並重新 ingest，**When** 再次執行抽取，**Then** response 的 source fingerprint 與 model metadata 可追溯本次輸入版本。

---

### User Story 2 - 儲存可追溯 extraction artifact（Priority: P1）

使用者或 agent 可以明確要求保存 LLM 抽取結果，讓 009/010/011 可重用同一份候選資料，而不必每次重新呼叫 LLM。保存行為不得等同 apply 到 wiki、graph 或 vector。

**Why this priority**: LLM output 成本高且不可完全重現；沒有 artifact，後續 feature 只能重新抽取，無法建立可稽核 pipeline。

**Independent Test**: 對 fixture source 執行 store mode，驗證 `$KS_ROOT/llm/extractions/` 產生 versioned artifact，artifact 包含 source fingerprint、schema version、prompt version、provider、model、created_at 與 validation status，且 response 回傳可供後續 feature 解析的 artifact reference。

**Acceptance Scenarios**:

1. **Given** preview 結果通過 schema validation，**When** caller 指定 store mode，**Then** 系統寫入 extraction artifact 並於 response 回傳 artifact reference。
2. **Given** 同一 source fingerprint、provider、model 與 prompt version 已有 artifact，**When** caller 未指定 force，**Then** 系統回傳既有 artifact 或明確標示 idempotent reuse。
3. **Given** artifact store 寫入中斷，**When** 執行 `ks lint` 或 feature-specific lint check，**Then** 系統能偵測 partial / corrupt artifact。

---

### User Story 3 - Agent 透過 CLI / MCP / HTTP 使用同一能力（Priority: P2）

Codex、Claude、OpenClaw 或其他 agent 可以透過 CLI、MCP 或 loopback HTTP 取得同一份 LLM classification/extraction contract，不需要自行解析 prompt output 或維護 provider-specific schema。

**Why this priority**: HKS 已把 MCP / HTTP adapter 視為正式 agent-facing surface；008 若只支援 CLI，agent 生態會產生分裂 contract。

**Independent Test**: 使用同一 fixture runtime，透過 CLI、in-process MCP tool 與 loopback HTTP endpoint 呼叫 fake provider，驗證三者 response 的 extraction detail 在語意上等價。

**Acceptance Scenarios**:

1. **Given** agent client 透過 MCP 呼叫 LLM extraction，**When** provider 為 fake 且 source 存在，**Then** MCP response 與 CLI response 共用同一 detail schema。
2. **Given** HTTP facade 綁定 non-loopback host，**When** 啟動 LLM extraction endpoint，**Then** 預設拒絕，沿用 006 local-first safety boundary。
3. **Given** hosted provider 未 explicit opt-in，**When** agent 要求使用 hosted provider，**Then** 系統拒絕並回傳可解析錯誤。

### Edge Cases

- `KS_ROOT` 尚未初始化或 source relpath 不存在。
- source 存在但未出現在 manifest，無法取得 parser fingerprint 或 source fingerprint。
- provider disabled、provider timeout、provider 回傳非 JSON、schema validation fail。
- provider 回傳 entity / relation 類型不在 HKS graph schema 最小集合內。
- evidence span 指向不存在 chunk、offset 越界或 raw source fingerprint 不匹配。
- extraction artifact 已存在但 schema version / prompt version / provider model 不同。
- hosted provider 被設定但缺少 explicit opt-in 或必要 credential。
- 同一 source 被兩個 agent 同時 store extraction artifact。
- LLM output 嘗試要求自動寫入 wiki / graph / vector。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an LLM-assisted classification/extraction capability for already ingested HKS sources.
- **FR-002**: System MUST expose a CLI namespace for this feature as `ks llm classify`; implementation MAY add subcommands only if they preserve this primary entry point.
- **FR-003**: Successful CLI / MCP / HTTP responses MUST preserve the existing HKS top-level JSON shape: `answer`, `source`, `confidence`, `trace`.
- **FR-004**: The feature MUST add a versioned `trace.steps[kind="llm_extraction_summary"]` detail schema under this spec's contracts.
- **FR-005**: LLM extraction output MUST include classification labels, summary candidate, key facts, entity candidates, relation candidates, confidence, evidence, source fingerprint, prompt version, provider id, model id, and validation status.
- **FR-006**: Entity candidates MUST be normalized to the stable HKS entity type set: `Person`, `Project`, `Document`, `Event`, `Concept`; unsupported types MUST be rejected or mapped with explicit evidence.
- **FR-007**: Relation candidates MUST be normalized to the stable HKS relation set: `owns`, `depends_on`, `impacts`, `references`, `belongs_to`; unsupported relations MUST be rejected or mapped with explicit evidence.
- **FR-008**: Default mode MUST be preview/read-only and MUST NOT mutate `wiki/`, `graph/graph.json`, `vector/db/`, existing manifest entries, or write-back pages.
- **FR-009**: System MUST support an explicit store mode that writes a versioned extraction artifact under `$KS_ROOT/llm/extractions/` without applying it to wiki / graph / vector.
- **FR-010**: Stored extraction artifacts MUST be idempotent by source fingerprint, parser fingerprint, prompt version, provider id, and model id unless caller explicitly requests a new run.
- **FR-011**: Stored extraction artifacts MUST be discoverable by later 009/010/011 features through a stable artifact reference returned in the response.
- **FR-012**: Provider configuration MUST be local-first: no network call is allowed unless caller explicitly selects a hosted provider and satisfies its opt-in configuration.
- **FR-013**: Tests MUST use a deterministic fake provider and MUST NOT require network, paid API keys, or hosted LLM services.
- **FR-014**: Provider failures, malformed output, timeout, validation errors, and missing credentials MUST return parseable JSON with HKS exit code semantics. Mapping rules are enumerated in the "Error → Exit Code Mapping (FR-014)" table at the end of this section.
- **FR-015**: The feature MUST not implement wiki synthesis, Graphify clustering/visualization/audit report, watch/daemon scheduling, UI, RBAC, cloud sync, or microservice deployment.
- **FR-016**: MCP and HTTP adapters MUST expose the same capability if this feature adds a public agent surface; success payloads MUST NOT introduce adapter-specific envelopes.
- **FR-017**: Any extension to canonical `trace.steps.kind`, CLI exit code mapping, runtime layout, or adapter contract MUST be documented in `docs/main.md`, README files, and contract tests during implementation.
- **FR-018**: LLM prompts and provider adapters MUST be domain-agnostic; no hard-coded legal, medical, code, or company-specific taxonomy is allowed.
- **FR-019**: The extraction artifact MUST record enough provenance for audit: original source relpath, raw source fingerprint, parser fingerprint, prompt version, provider id, model id, generated_at, schema version, and `status`.
- **FR-020**: The feature MUST fail closed when an LLM asks for side effects; side-effect text in model output cannot trigger writes outside explicit store mode.
- **FR-021**: Successful 008 responses MUST set `trace.route="wiki"` and `source=[]` in order to stay within the current constitution §II route/source enum while limiting the contract change to the planned MINOR `trace.steps.kind="llm_extraction_summary"` extension. Spec consumers MUST treat `source=[]` together with `trace.steps[kind="llm_extraction_summary"]` as a successful extraction (NOT a no-hit). This semantic divergence from `ks query` (where `source=[]` means no hit) MUST be documented in `docs/main.md` and README during implementation.
- **FR-022**: Hosted/network providers MUST be gated by environment variables only — concretely all of: `HKS_LLM_NETWORK_OPT_IN=1`, `HKS_LLM_PROVIDER_<ID>_API_KEY` (provider-specific credential, where `<ID>` is the upper-cased `provider_id`), and optionally `HKS_LLM_PROVIDER_<ID>_ENDPOINT`. CLI flags, MCP request fields, and HTTP request bodies MUST NOT expose any opt-in toggle. Missing any required gate MUST exit `2 USAGE` per FR-014.

#### Error → Exit Code Mapping (FR-014)

| Trigger | Exit code |
|---|---|
| `KS_ROOT` 未初始化 / source relpath 不存在 / 不在 manifest | `66` NOINPUT |
| 缺 opt-in / 缺 credential / `mode` 不合法 / 未支援的 provider | `2` USAGE |
| provider 回傳 malformed JSON / schema validation fail / 不支援的 entity/relation 型別 / evidence span 越界 | `65` DATAERR |
| provider timeout / network error / 其他 runtime 例外 | `1` GENERAL |
| 成功（含 fail-closed 拒絕 side-effect 但 emit valid response） | `0` OK |

新增 exit code 走憲法 §II MINOR 升級；008 沿用既有 5 個 code，不新增。

### Key Entities *(include if feature involves data)*

- **LlmProviderConfig**: Provider selection and safety settings, including provider id, model id, endpoint, timeout, network opt-in, and credential presence status.
- **LlmExtractionRequest**: A request to classify/extract one ingested source, including source relpath or source id, mode (`preview` or `store`), prompt version, and provider config reference.
- **LlmExtractionResult**: Schema-validated model output containing classification, summary candidate, key facts, entity candidates, relation candidates, confidence, evidence, and model metadata.
- **EntityCandidate**: A possible graph entity with normalized type, label, aliases, confidence, and evidence spans.
- **RelationCandidate**: A possible graph relation with normalized relation type, source entity reference, target entity reference, confidence, and evidence spans.
- **ExtractionArtifact**: Persisted result under `$KS_ROOT/llm/extractions/`, versioned by source fingerprint, parser fingerprint, prompt version, provider id, and model id.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For fixture sources, fake-provider preview responses pass canonical HKS response schema and 008 `llm_extraction_summary` schema 100% of the time.
- **SC-002**: Preview mode leaves wiki, graph, vector, and manifest content byte-for-byte unchanged in regression tests.
- **SC-003**: Store mode creates exactly one valid extraction artifact per idempotency key unless force/new-run is explicitly requested.
- **SC-004**: Malformed provider output, unsupported relation/entity type, missing source, and hosted-provider-without-opt-in each return parseable JSON and expected exit/error code.
- **SC-005**: CLI, MCP, and HTTP adapter responses for the same fake-provider fixture expose equivalent extraction detail fields.
- **SC-006**: Extraction artifacts include required provenance fields and can be resolved by later features without re-running provider inference.

## Assumptions

- 008 targets sources already processed by existing `ks ingest`; it is not a replacement for parsers, normalizer, embedding, or query routing.
- LLM output is advisory until later features explicitly apply it; human or agent review remains possible because evidence and provenance are preserved.
- Hosted LLM providers are optional adapters, not a required dependency or default path.
- `$KS_ROOT/llm/extractions/` is a new runtime area for candidate artifacts, separate from the authoritative wiki / graph / vector layers.
- 009 will consume summary/fact candidates for wiki synthesis, 010 will consume entity/relation/classification artifacts for Graphify, and 011 will orchestrate repeated execution.
