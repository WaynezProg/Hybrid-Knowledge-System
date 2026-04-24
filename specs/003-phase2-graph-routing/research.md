# Research: Phase 2 階段二 — Graph / Routing / Auto Write-back

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-24

## 1. Graph Persistence

**Decision**: 採 `graph.json`，不引入 graph DB。

**Rationale**:
- fixture 規模小，JSON 足夠
- local-first、離線可驗證
- 不增加 neo4j / networkx 類依賴

## 2. Relation Extraction

**Decision**: 先走 pattern-based extractor。

**Rationale**:
- 現有 fixtures 已有 `影響 / 依賴 / affects / depends on`
- 可測試、可回歸、可離線
- 後續要接更強模型，不必推翻 graph store

## 3. Routing Backend

**Decision**: 預設用本機 deterministic semantic router；`HKS_ROUTING_MODEL` 只當 backend 標記 / 未來擴充點。

**Rationale**:
- 原始 doc 沒指定 provider
- hosted API 會破壞 local-first
- 測試需要 deterministic

## 4. Auto Write-back

**Decision**: 以 `HKS_WRITEBACK_AUTO_THRESHOLD=0.75` 作為預設門檻。

**Rationale**:
- 可觀測、可覆寫
- `--writeback=no` 仍能完全關閉
- 能把 Phase 2 的「全自動」收斂成可控策略，而不是靜默亂寫
