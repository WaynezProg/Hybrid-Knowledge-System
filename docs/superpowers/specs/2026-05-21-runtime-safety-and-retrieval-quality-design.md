# Runtime Safety and Retrieval Quality Sequencing Design

> **Date:** 2026-05-21
> **Status:** Draft
> **Depends on:** 013-pageindex-integration

## Problem Statement

HKS 已經有 spec-first workflow、schema、strict typing、CI、offline replay、fused retrieval、PageTree 與 workspace registry。下一階段不該再用「功能增強」描述，因為真正風險不是缺功能，而是 runtime 掛給 agent 長期使用時會污染資料或跨 workspace 串台。

目前高風險集中在三個面向：

1. `confidence` 同時代表 wiki hard score、graph heuristic、vector similarity、page_tree overlap，但 auto write-back 直接拿這個值判斷是否寫入 wiki。
2. adapter / workspace scoped query 透過 `os.environ["KS_ROOT"]` 切換 runtime root；HTTP / ASGI 併發下這是 process-global race。
3. query 已有 basic eval，但還沒有足以阻擋 retrieval 退化、no-hit 誤判、writeback false positive 的品質門檻。

## Sequencing Decision

按 repo 編號往下排，不跳號：

| Feature | Name | Goal |
|---|---|---|
| 014 | runtime-isolation-security | 防止跨 workspace 串台、HTTP 未授權 mutation、HTTP ingest 任意讀檔 |
| 015 | confidence-writeback-gate | 把 raw retrieval score 與可回寫信心切開，讓 writeback gate 有 evidence 條件 |
| 016 | retrieval-quality-gate | 在 CI 補 quick eval gate，量測 route / evidence / no-hit / writeback false positive |
| 017 | query-refactor | 在 safety 與 eval gate 後拆 query.py，避免重構時失去行為證據 |

這個順序刻意把安全與資料污染放在重構前。重構不能先做，因為它只會把未校準 confidence、env race、HTTP unsafe surface 分散到更多檔案。

## 014: Runtime Isolation and HTTP Security

### Scope

`014-runtime-isolation-security` 只處理 runtime boundary，不改 retrieval ranking、不改 confidence semantics。

核心改動：

1. 新增 request-scoped `KS_ROOT` contextvar。
2. `runtime_paths()` / `resolve_ks_root()` 優先讀 explicit arg，其次 contextvar，其次 config/env，最後 cwd fallback。
3. adapter core 與 workspace query 不再改 `os.environ["KS_ROOT"]`。
4. HTTP facade 新增 Bearer token、Host header allowlist、browser-style request block。
5. HTTP ingest path 改成 workspace-relative / allowed-root relative path，不接受 arbitrary absolute path。

### Runtime Root Contract

新增 `hks.core.runtime_context`：

```python
current_ks_root: ContextVar[str | None]

@contextmanager
def scoped_ks_root(ks_root: str | Path | None) -> Iterator[None]:
    ...
```

`resolve_ks_root(root=None)` precedence：

1. explicit `root`
2. contextvar `current_ks_root`
3. `config_value("KS_ROOT")`
4. `Path.cwd() / "ks"`

CLI 行為不變：CLI 可以繼續靠 env/config 決定 `KS_ROOT`。adapter 行為改成 context-local：同 process 多 request 不會互相覆蓋。

**統一舊實作**：`adapters/core.py` 和 `workspace/service.py` 各自有一份 `scoped_ks_root()` 直接改 `os.environ`。014 完成後這兩處必須刪除，統一至 `hks.core.runtime_context.scoped_ks_root()`。

**MCP adapter 遷移**：`hks-mcp` 同樣遷移至 contextvar-based `scoped_ks_root()`。MCP 是 stdio transport，不需要 bearer token 或 Host check，但 ingest path validation 應與 CLI 一致。

### HTTP Security Contract

新增 config/env：

- `HKS_API_TOKEN`
- `HKS_API_HOST_ALLOWLIST`，預設 `127.0.0.1,localhost,::1`
- `HKS_API_REJECT_BROWSER_REQUESTS`，預設 true
- `HKS_API_INGEST_ROOTS`，預設空，格式為 `id=/absolute/source/root` 的逗號分隔清單

HTTP request guard（以 Starlette middleware 實作，不在 endpoint function 中重複）：

- Host header 必須在 allowlist。
- mutating endpoint 需要 `Authorization: Bearer <HKS_API_TOKEN>`。
- 若 request 含 `Origin` 或 `Sec-Fetch-Site`，預設拒絕，除非 config 明確關閉。

Mutating endpoints：

- `/ingest`
- `/llm/classify`
- `/wiki/synthesize`
- `/graphify/build`
- `/watch/run`
- `/workspaces` 的 `register`
- `/workspaces/{workspace_id}` 的 `remove`
- `/coord/session`
- `/coord/lease`
- `/coord/handoff`

Read-only endpoints 可以在 loopback + Host allowlist 下免 token，但若設定 `HKS_API_TOKEN`，仍接受 token 並記錄 trace。

### HTTP Ingest Path Contract

HTTP `hks_ingest` 不再接受 arbitrary path。request 必須提供：

- `workspace_id` 或 `ks_root`，用來選擇目標 HKS runtime。
- `source_root_id`，對應 `HKS_API_INGEST_ROOTS` 的 named root；若只設定一個 root 可省略。
- `path`，必須是相對於 selected source root 的 relative path。

規則：

- 禁止 absolute path。
- 若 `HKS_API_INGEST_ROOTS` 未設定，HTTP `/ingest` 回 `403`，不提供 fallback 到 cwd 或 home。
- `Path.resolve(strict=False)` 後不得 symlink escape。
- 跳過 `.git`、`.ssh`、`.env`、`node_modules`、`.venv`、`__pycache__`。
- 只允許已支援副檔名。
- CLI ingest 不套用 HTTP path allowlist，維持本機工具語意。

### 014 Tests

- unit: contextvar precedence and restore behavior
- unit: 舊 `adapters/core.py` 和 `workspace/service.py` 的 `scoped_ks_root` 已移除，import 改指向 `runtime_context`
- integration: two concurrent adapter calls with different `ks_root` cannot see each other
- integration: MCP adapter 使用 contextvar-based `scoped_ks_root`
- HTTP contract: missing token blocks mutating endpoint
- HTTP contract: invalid Host blocks request
- HTTP contract: Origin / Sec-Fetch-Site browser request blocks mutating endpoint
- HTTP contract: security guards 由 middleware 處理，非 per-endpoint 重複
- HTTP ingest: absolute path and symlink escape rejected

## 015: Confidence and Writeback Gate

### Scope

`015-confidence-writeback-gate` 改 query response semantics 與 writeback decision，不拆 query modules。

目前 `confidence` 是 mixed raw score。015 後：

- `confidence` **值不動**，保持原始 raw score，確保既有 agent/script 的行為不因 015 上線而 silent break。
- 新增 optional top-level `retrieval_score`（= raw score，與 `confidence` 等值；為未來 deprecation `confidence` 鋪路）。
- 新增 optional top-level `calibrated_confidence`（校準後信心）。
- 新增 optional top-level `writeback_eligible`（bool）。
- writeback gate 改讀 `calibrated_confidence`，不再讀 `confidence`。
- 不新增 top-level `route`，因為 `trace.route` 已是 authoritative selected route；重複欄位會增加 drift 風險。

> **設計決策**：曾考慮直接把 `confidence` 值改成 calibrated score，但這對已依賴舊值的 caller 是 silent behavior change，不符合 backward compatibility 承諾。選擇 additive-only schema evolution。

### Calibration Contract

新增 `src/hks/retrieval/confidence.py`（直接建立在 017 的目標路徑，避免二次搬遷）：

```python
@dataclass(frozen=True, slots=True)
class ConfidenceAssessment:
    retrieval_score: float
    calibrated_confidence: float
    writeback_eligible: bool
    reasons: list[str]
```

Route policy：

| Route | Auto writeback eligibility |
|---|---|
| wiki | default false，除非 explicit `--writeback=yes` |
| graph | 需要 edge ids、edge evidence、source_relpath、calibrated threshold |
| vector | 需要 source_relpath、quote、similarity threshold、non-empty evidence |
| page_tree | 需要 source_relpath、section_path、page_range、non-empty quote |

> **預期效果**：graph extraction 目前是 regex/heuristic，很多 edge 缺乏 `raw_evidence` 或完整 `source_relpath`。015 上線後 graph route 的 auto writeback 會**事實上接近永遠 false**。這是刻意的防污染結果，不是 bug。Graph extraction 品質提升後（deferred: graph edge provenance），auto writeback 自然會開始通過。

`--writeback=yes` 仍是 explicit caller mutation，可以越過 auto eligibility，但 trace 必須標示 `"forced": true`。forced writeback 同時寫入 coordination `events.jsonl`，讓 `ks lint` 能偵測非自然回寫。

> **Status:** Implemented — see `docs/superpowers/plans/2026-05-22-015-confidence-writeback-gate.md`.

### Rerank Trace Contract

LLM rerank fallback 不再靜默。`merge` 或新增 `rerank` trace step 必須包含：

```json
{
  "kind": "rerank",
  "detail": {
    "strategy": "llm",
    "status": "fallback",
    "fallback_strategy": "rrf",
    "reason": "openai_timeout"
  }
}
```

Reason enum 初版：

- `provider_not_ready`
- `credential_missing`
- `openai_timeout`
- `openai_http_error`
- `openai_invalid_json`
- `openai_invalid_ranking`
- `unexpected_error`

### 015 Tests

- contract: optional confidence fields validate against schema
- unit: wiki auto writeback ineligible
- unit: vector requires source_relpath + quote + similarity threshold
- unit: graph requires edge evidence
- unit: page_tree requires section_path + page_range
- integration: `writeback=auto` never writes when `writeback_eligible=false`
- unit: LLM rerank fallback reason appears in trace

## 016: Retrieval Quality Gate

### Scope

`016-retrieval-quality-gate` builds on the existing `evals/` and `tests/eval/`. It does not replace them.

Existing evals prove the fused path runs. 016 adds measurable pass/fail quality metrics:

- `route_accuracy`
- `precision_at_1`
- `evidence_hit_rate`
- `no_hit_precision`
- `writeback_false_positive_rate`

### 與現有 Eval 的關係

現有 `evals/e2e_query.jsonl`（5 筆，格式為 `expected_sources_present` + `expected_answer_contains`）和 `tests/eval/test_e2e_query_eval.py` 繼續保留並在 CI 中跑。它們驗證 fused path 不壞；016 新增的 golden query eval 驗證品質指標。兩者格式不同、threshold 獨立、CI 中並行執行。

### Golden Query Format

新增 `evals/golden_queries/*.jsonl`（與現有 `evals/` 並存）：

```json
{
  "id": "vector-fact-001",
  "question": "Who owns Project Atlas?",
  "expected_route": "vector",
  "expected_source_relpath": "project-atlas.txt",
  "expected_evidence_quote": "Owner Iris",
  "writeback_allowed": false
}
```

Initial categories:

- wiki summary
- vector fact lookup
- graph relation
- page_tree section lookup
- no-hit
- multi-source conflict

### CI Gate

CI runs a deterministic quick eval with `HKS_EMBEDDING_MODEL=simple` and no OpenAI key. Thresholds are intentionally conservative for first adoption:

- route_accuracy >= 0.70
- evidence_hit_rate >= 0.80
- no_hit_precision = 1.00
- writeback_false_positive_rate = 0.00

> **no_hit_precision = 1.00 的前提**：no-hit 案例必須是真正無歧義的問題（知識庫中不存在任何相關資料）。如果 question 本身有歧義或能被偶然命中，100% threshold 會讓 CI 脆弱。撰寫 no-hit 案例時，先用 `ks query` 驗證確實沒有任何 route 命中。

> **simple embedding + lexical filter 交互**：CI 在 `HKS_EMBEDDING_MODEL=simple` 下跑，vector similarity 品質較低，此時 `_vector_hit_is_relevant()` 的 lexical hard gate 會更頻繁地丟掉本應命中的結果。若 016 eval 的 `evidence_hit_rate` 持續無法達標，應考慮將 vector lexical filter softening（目前在 deferred）提前到 016 scope。

Hosted OpenAI eval remains opt-in and is not required for CI.

### 016 Tests

- unit: metric computation
- integration: quick golden eval fixture passes
- regression: no-hit questions produce no writeback eligibility
- CI: add one quick eval command after pytest or as a targeted pytest module

## 017: Query Refactor

### Scope

`017-query-refactor` only starts after 014-016 are green. It changes module boundaries, not public behavior.

Target structure:

```text
src/hks/retrievers/wiki.py
src/hks/retrievers/graph.py
src/hks/retrievers/vector.py
src/hks/retrievers/page_tree.py
src/hks/rerank/rrf.py
src/hks/rerank/llm.py
src/hks/retrieval/confidence.py
src/hks/commands/query.py
```

`commands/query.py` becomes orchestration only:

1. load runtime paths and manifest
2. collect route candidates
3. rerank
4. assess confidence
5. build response
6. call writeback gate

### Guardrails

- No public schema change in 017.
- Existing 016 golden eval must pass before and after refactor.
- Private function tests that import old query internals should migrate to module-level tests.
- Keep RRF behavior byte-for-byte equivalent unless a 016 eval explicitly proves the old behavior wrong.

## Deferred Work

These are real, but not part of 014-017:

- Vector lexical filter softening and final-score feature exposure. **提前條件**：若 016 CI eval 的 `evidence_hit_rate` 在 `simple` embedding 下持續無法達標，應提前到 016 scope 內處理。
- Embedding collection versioning by provider/model/dimension/chunker fingerprint.
- Graph edge provenance fields: extraction_method, pattern_id, raw_evidence, source_span, verified.
- Ingest transaction journal and crash recovery.
- OpenAI chat / embedding client unification.
- OCR subprocess timeout.
- Python 3.13 CI matrix.
- `ks = "hks.cli:main"` entrypoint migration.
- Ruff BLE001 adoption.
- Graphify HTML template extraction.

They should become separate numbered specs after 017, because each touches a different blast radius.

## Alternatives Considered

### One large `015-runtime-safety-and-retrieval-quality`

Rejected. It would mix security, response schema, eval infrastructure, retrieval behavior, and refactor in one PR. That makes rollback unsafe and makes regressions hard to localize.

### Refactor query first

Rejected. Refactor before safety/eval only makes the current confidence and writeback bugs harder to pin down.

### Add only evals before safety

Rejected. Evals do not prevent HTTP adapter mutation or cross-workspace runtime race. Runtime boundary fixes must happen first.

## Acceptance Gates

Each numbered feature must pass:

- `uv run pytest --tb=short -q`
- `uv run ruff check .`
- `uv run mypy src/hks`

Feature-specific gates:

- 014: concurrent workspace adapter smoke + HTTP security contract tests
- 015: auto writeback false-positive tests
- 016: quick golden retrieval eval in CI
- 017: 016 eval passes before and after refactor

## Handoff

After this design is approved, implementation planning should start with `014-runtime-isolation-security` only. Do not begin 015 until 014 is merged or explicitly closed, because 015 depends on adapter/root isolation being trustworthy.
