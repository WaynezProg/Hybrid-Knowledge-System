---
description: "Phase 2 階段二 — Graph Query、Model-Driven Routing、Auto Write-back 任務清單"
---

# Tasks: Phase 2 階段二 — Graph Query、Model-Driven Routing、Auto Write-back

**Input**: [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts/) · [quickstart.md](./quickstart.md)
**Prerequisites**: `001-phase1-cli-mvp`、`002-phase2-ingest-office`
**Tests**: 本 feature 必須有 contract / integration / smoke 驗證
**Organization**: 依 speckit 慣例分 Setup / Foundational / User Story / Polish

## Phase 1: Setup

- [x] T001 建立 `specs/003-phase2-graph-routing/contracts/query-response.schema.json`
- [x] T002 補 `spec / plan / research / data-model / quickstart / tasks`

## Phase 2: Foundational

- [x] T010 擴充 `src/hks/core/schema.py` 與 `src/hks/core/paths.py`，開放 `graph` route/source 與 `/ks/graph/graph.json`
- [x] T011 擴充 `src/hks/core/manifest.py`，derived artifacts 補 `graph_nodes / graph_edges`
- [x] T012 新增 `src/hks/graph/store.py`
- [x] T013 新增 `src/hks/graph/extract.py`
- [x] T014 新增 `src/hks/graph/query.py`

## Phase 3: User Story 1 — Graph Query（P1）

- [x] T020 更新 `src/hks/ingest/pipeline.py`，同步 graph / rollback / prune
- [x] T021 更新 `src/hks/commands/query.py`，relation query 先查 graph、miss 再 fallback vector
- [x] T022 更新 `tests/contract/test_json_schema.py`、新增 `tests/contract/test_graph_runtime.py`
- [x] T023 更新 `tests/integration/test_query_flows.py`、`tests/integration/test_query_office_hits.py`

## Phase 4: User Story 2 — Model-Driven Routing（P1）

- [x] T030 更新 `src/hks/routing/router.py` 為 semantic routing backend
- [x] T031 更新 `src/hks/routing/rules.py` 與 `config/routing_rules.yaml`
- [x] T032 更新 `tests/unit/routing/test_rules.py`、`tests/unit/routing/test_router.py`

## Phase 5: User Story 3 — Auto Write-back（P2）

- [x] T040 更新 `src/hks/writeback/gate.py`，預設改 `auto`
- [x] T041 更新 `src/hks/writeback/writer.py`，補 related cross-links
- [x] T042 更新 `src/hks/storage/wiki.py` 與 `src/hks/cli.py`
- [x] T043 更新 `tests/unit/writeback/test_gate.py`、`tests/unit/writeback/test_writer.py`、`tests/integration/test_writeback.py`

## Phase 6: Polish

- [x] T050 更新 `README.md`、`README.en.md`、`docs/main.md`、`docs/PRD.md`
- [x] T051 執行 `uv run pytest -q`
- [x] T052 執行 `uv run ruff check .`
- [x] T053 執行 `uv run mypy src/hks`
- [x] T054 執行真實 CLI smoke（ingest → relation query → auto write-back）
