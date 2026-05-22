# Spec Archive

這份索引用來標示已完成的 speckit feature artifacts。

封存策略：
- 已完成 feature 採 **archived in place**，不搬移 `specs/<feature-branch>/` 目錄。
- 原路徑保留是為了維持 README、docs、cross-spec links 與 speckit artifact 參照穩定。
- 封存後原則上不再修改內容；若需修正，只接受勘誤、連結修補、或 post-merge retrospective 註記。

## Active

- `019-writeback-review-queue`
  - Status: Design approved, implementation pending
  - Canonical artifacts: [spec.md](./019-writeback-review-queue/spec.md), [plan.md](./019-writeback-review-queue/plan.md), [tasks.md](./019-writeback-review-queue/tasks.md)
  - Runtime note: current `ks query --writeback=auto|yes` still uses direct wiki write-back; queue commands are not implemented yet.

## Implemented local gates

- `014-runtime-isolation-security`
  - Status: Complete
  - Implemented on: 2026-05-21
  - Canonical artifacts: [plan](../docs/superpowers/plans/2026-05-21-014-runtime-isolation-security.md)
- `015-confidence-writeback-gate`
  - Status: Complete
  - Implemented on: 2026-05-22
  - Canonical artifacts: [plan](../docs/superpowers/plans/2026-05-22-015-confidence-writeback-gate.md)
- `016-retrieval-quality-gate`
  - Status: Complete
  - Implemented on: 2026-05-22
  - Canonical artifacts: [plan](../docs/superpowers/plans/2026-05-22-016-retrieval-quality-gate.md), [golden queries](../evals/golden_queries/quick.jsonl), [eval test](../tests/eval/test_golden_retrieval_quality.py)
- `017-query-refactor`
  - Status: Complete
  - Implemented on: 2026-05-22
  - Canonical artifacts: [plan](../docs/superpowers/plans/2026-05-22-017-query-refactor.md), [retrievers](../src/hks/retrievers), [rerank](../src/hks/rerank)

## Archived

- `001-phase1-cli-mvp`
  - Status: Complete
  - Archived on: 2026-04-25
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./001-phase1-cli-mvp/spec.md), [plan.md](./001-phase1-cli-mvp/plan.md), [tasks.md](./001-phase1-cli-mvp/tasks.md)
- `002-phase2-ingest-office`
  - Status: Complete
  - Archived on: 2026-04-25
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./002-phase2-ingest-office/spec.md), [plan.md](./002-phase2-ingest-office/plan.md), [tasks.md](./002-phase2-ingest-office/tasks.md)
- `003-phase2-graph-routing`
  - Status: Complete
  - Archived on: 2026-04-25
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./003-phase2-graph-routing/spec.md), [plan.md](./003-phase2-graph-routing/plan.md), [tasks.md](./003-phase2-graph-routing/tasks.md)
- `004-phase3-image-ingest`
  - Status: Complete
  - Archived on: 2026-04-25
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./004-phase3-image-ingest/spec.md), [plan.md](./004-phase3-image-ingest/plan.md), [tasks.md](./004-phase3-image-ingest/tasks.md)
- `005-phase3-lint-impl`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./005-phase3-lint-impl/spec.md), [plan.md](./005-phase3-lint-impl/plan.md), [tasks.md](./005-phase3-lint-impl/tasks.md)
- `006-mcp-api-adapter`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./006-mcp-api-adapter/spec.md), [plan.md](./006-mcp-api-adapter/plan.md), [tasks.md](./006-mcp-api-adapter/tasks.md)
- `007-multi-agent-support`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./007-multi-agent-support/spec.md), [plan.md](./007-multi-agent-support/plan.md), [tasks.md](./007-multi-agent-support/tasks.md)
- `008-llm-classification-extraction`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./008-llm-classification-extraction/spec.md), [plan.md](./008-llm-classification-extraction/plan.md), [tasks.md](./008-llm-classification-extraction/tasks.md)
- `009-llm-wiki-synthesis`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./009-llm-wiki-synthesis/spec.md), [plan.md](./009-llm-wiki-synthesis/plan.md), [tasks.md](./009-llm-wiki-synthesis/tasks.md)
- `010-graphify-pipeline`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./010-graphify-pipeline/spec.md), [plan.md](./010-graphify-pipeline/plan.md), [tasks.md](./010-graphify-pipeline/tasks.md)
- `011-continuous-watch`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./011-continuous-watch/spec.md), [plan.md](./011-continuous-watch/plan.md), [tasks.md](./011-continuous-watch/tasks.md)
- `012-source-catalog`
  - Status: Complete
  - Archived on: 2026-04-26
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./012-source-catalog/spec.md), [plan.md](./012-source-catalog/plan.md), [tasks.md](./012-source-catalog/tasks.md)
- `013-pageindex-integration`
  - Status: Complete
  - Archived on: 2026-05-23
  - Merged into: `main`
  - Canonical artifacts: [spec.md](./013-pageindex-integration/spec.md), [plan.md](./013-pageindex-integration/plan.md), [ARCHIVE.md](./013-pageindex-integration/ARCHIVE.md)
