# Feature Specification: Phase 2 階段二 — Graph Query、Model-Driven Routing、Auto Write-back

**Feature Branch**: `003-phase2-graph-routing`
**Created**: 2026-04-24
**Status**: Complete
**Input**: 補齊 [docs/main.md](../../docs/main.md) 與 [docs/PRD.md](../../docs/PRD.md) 原先定義、但 `001` / `002` 尚未完成的剩餘 Phase 2 能力：graph extraction / graph query、routing 升級為 model-driven、預設全自動 write-back。保留 local-first，不綁 hosted API；`lint`、OCR / VLM、多 agent、API / MCP adapter 仍屬 Phase 3，不在本 spec 範圍。對應憲法 [§II / §IV / §V](../../.specify/memory/constitution.md)。

## Clarifications

### Session 2026-04-24

- Q: `003` 是否再新增 ingest 格式 → A: 不新增；Phase 2 的格式全集固定為 `txt / md / pdf / docx / xlsx / pptx`。圖片 ingest 仍屬後續 Phase 3 spec，但實際接受格式與 normalize / 轉檔策略尚未凍結，不在 `003` 先做死
- Q: 「model-driven routing」是否要求 hosted LLM → A: 不要求；repo 預設以本機 deterministic semantic router 落地，`HKS_ROUTING_MODEL` 只作 backend 標記與未來擴充點
- Q: `auto write-back` 在 automation / non-TTY 的預設 → A: runtime 預設仍為 `auto`，但 CI / smoke / agent workflow 以顯式 `--writeback=no` 關閉；非 TTY 不得因互動邏輯阻塞
- Q: graph extraction 的能力邊界 → A: 先支撐 fixture 與 regression tests 的 pattern-based entity / relation 抽取；不在本 spec 擴成通用 NLP 或 hosted inference pipeline

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Relation Query 直接走 Graph（Priority: P1）

使用者在 ingest 完含關係句的文件後，執行 relation / impact / dependency / why 類 query，系統能優先命中 graph layer，而不是再用 Phase 1 的 vector fallback 假裝回答。

**Why this priority**：這是 Phase 2 跟 Phase 1 的核心差異；沒有 graph query，就不算 Phase 2 完成。

**Independent Test**：對已 ingest 的 fixture 執行 `uv run ks query "A 專案延遲影響哪些系統" --writeback=no`，驗證 `trace.route=="graph"`、`source==["graph"]`，且 `KS_ROOT/graph/graph.json` 存在並可 JSON parse。

**Acceptance Scenarios**：

1. **Given** 已 ingest 含 `影響 / 依賴 / affects / depends on` 句型的文件，**When** 執行 relation 類 query，**Then** 系統優先走 graph，JSON `trace.steps` 包含 `routing_model` 與 `graph_lookup`。
2. **Given** graph 有資料但該問題無對應 edge，**When** 執行 relation 類 query，**Then** 系統 fallback 至 vector，`trace.steps` 記錄 `fallback from graph to vector`。
3. **Given** re-ingest 更新來源檔內容，**When** graph 重建，**Then** 舊 edge 不得殘留於 `graph.json`。

---

### User Story 2 — Query Routing 升級但仍離線可跑（Priority: P1）

agent 或使用者執行 query 時，routing 不再只是直接 keyword if/else，而是透過 routing backend 做 model-driven 決策；但 repo 預設仍必須在離線環境可驗證。

**Why this priority**：Phase 2 原始 doc 要求 routing 升級；如果還是純 Phase 1 rule match，只是加 graph store，不算補齊。

**Independent Test**：執行 summary / detail / relation 三類 query，驗證 `trace.steps[0].kind == "routing_model"`；全量測試在 `HKS_EMBEDDING_MODEL=simple` 下仍可通過。

**Acceptance Scenarios**：

1. **Given** summary 類問題，**When** 查詢，**Then** routing backend 仍可把請求導到 wiki。
2. **Given** detail 類問題，**When** 查詢，**Then** routing backend 導到 vector。
3. **Given** relation 類問題，**When** 查詢，**Then** routing backend 導到 graph；若無命中，再由 pipeline fallback vector。

---

### User Story 3 — 高 Confidence 預設自動 Write-back（Priority: P2）

使用者在不顯式指定 `--writeback` 的情況下，對高 confidence 問題執行 query，系統會自動寫回 wiki，並在新頁面加上 related cross-links。

**Why this priority**：這是原始 Phase 2 定義的一部分，但即使不做，也不影響 graph query 本身，所以列 P2。

**Independent Test**：執行 `uv run ks query "summary Atlas"`，驗證 `trace.steps` 中 `writeback.status=="auto-committed"`，且新 wiki page 含 `## Related`。

**Acceptance Scenarios**：

1. **Given** `confidence >= HKS_WRITEBACK_AUTO_THRESHOLD`，**When** 未帶 `--writeback` 執行 query，**Then** 系統自動回寫 wiki。
2. **Given** `--writeback=no`，**When** 執行 query，**Then** 即使高 confidence 也不得寫回。
3. **Given** write-back 成功，**When** 開啟新頁面，**Then** 內容含 related links 指向本次答案涉及的既有 wiki pages。

---

### Edge Cases

- graph 有節點但沒有對應 edge 時，relation query 必須 fallback vector，不可直接回 no-hit。
- re-ingest / prune / rollback 不得留下孤兒 graph nodes 或 stale edges。
- 非 TTY workflow 不能因 `auto` write-back 阻塞。
- routing backend 預設必須能在離線環境執行；未指定 provider 時不得偷呼叫外網。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-301**：`ks ingest` 成功後 MUST 產生 `/ks/graph/graph.json`，並把本次來源檔抽出的 entities / relations 同步寫入 graph layer。
- **FR-302**：graph schema 最小集合 MUST 固定為 `Person / Project / Document / Event / Concept` 與 `owns / depends_on / impacts / references / belongs_to`。
- **FR-303**：query top-level JSON contract MUST 維持 `answer / source / confidence / trace` 四欄，但 `source` 與 `trace.route` MUST 擴充允許 `graph`。
- **FR-304**：relation / impact / dependency / why 類問題 MUST 先嘗試 graph；graph 無命中時 MUST fallback vector。
- **FR-305**：routing 決策 MUST 經由 routing backend 產生，不再直接用單純 keyword 規則短路。repo 預設 backend MUST 為本機 deterministic semantic router；`HKS_ROUTING_MODEL` 僅作 backend 標記與未來擴充點。
- **FR-306**：`ks query` 預設 write-back 模式 MUST 為 `auto`。當 `confidence >= HKS_WRITEBACK_AUTO_THRESHOLD`（預設 `0.75`）時 MUST 自動寫回 wiki；`--writeback=no` MUST 禁用；`--writeback=yes` MUST 強制寫入；`--writeback=ask` MUST 保留互動式兼容。
- **FR-307**：自動 write-back 產生的新 wiki 頁面 MUST 帶 `## Related` section，連回本次答案涉及的既有 wiki pages。
- **FR-308**：manifest idempotency 除了 wiki / vector artifacts，還 MUST 追蹤 graph artifacts；re-ingest / prune / rollback 不得留下髒 graph。
- **FR-309**：`ks lint` 仍 MUST 維持 Phase 3 stub，不因本 spec 改動。

### Key Entities

- **GraphNode**：graph layer 內的 entity 節點，含 `id / type / label / aliases / source_relpaths / wiki_slugs`。
- **GraphEdge**：graph layer 內的 relation 邊，含 `relation / source / target / source_relpath / evidence`。
- **GraphPayload**：`graph.json` 的持久化根物件，含 `version / nodes / edges`。
- **WritebackContext**：query write-back 時攜帶的 related wiki page 上下文。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-301**：relation query 會回 `trace.route="graph"`，且 `source=["graph"]` 或 graph miss 後 `["vector"]`。
- **SC-302**：ingest 後 `KS_ROOT/graph/graph.json` 存在且可被標準 JSON parser 解析。
- **SC-303**：預設 `ks query` 在高 confidence 情境會新增 write-back page，且頁面含 `## Related`。
- **SC-304**：`uv run pytest -q`、`uv run ruff check .`、`uv run mypy src/hks` 全綠。

## Assumptions

- 本 repo 的 Phase 2 仍維持 local-first，不把 hosted LLM provider 當成必備前提。
- 現階段 graph extraction 先採 pattern-based，只要能穩定支撐 fixture 與 regression tests 即可。
- `001` 與 `002` 的既有 artifact 鏈仍是本 spec 的前置基線，不重做前兩張 spec。
