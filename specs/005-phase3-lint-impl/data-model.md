# Data Model: Phase 3 階段二 — `ks lint` 真實實作

## 1. Finding

最小 lint 結果單位。

```python
Finding(
    category: FindingCategory,
    severity: Severity,
    target: str,
    message: str,
    details: dict[str, object] = {},
)
```

### Category enum

- `orphan_page`
- `dead_link`
- `duplicate_slug`
- `manifest_wiki_mismatch`
- `wiki_source_mismatch`
- `dangling_manifest_entry`
- `orphan_raw_source`
- `manifest_vector_mismatch`
- `orphan_vector_chunk`
- `graph_drift`
- `fingerprint_drift`

### Severity enum

- `error`
- `warning`
- `info`

### Validation rules

- `category` MUST 為 enum。
- `severity` MUST 為 enum。
- `target` MUST 非空，使用 slug / relpath / chunk id / node id / edge id。
- `message` MUST 為單行文字，不含 ANSI / 控制字元。
- `details` 可選，但不得取代四個必填欄位。

## 2. FixAction

`--fix` 模式下的可執行或已執行修復動作。

```python
FixAction(
    action: FixActionKind,
    target: str,
    outcome: FixOutcome,
    details: dict[str, object] = {},
)
```

### Action enum

- `rebuild_index`
- `prune_orphan_vector_chunks`
- `prune_orphan_graph_nodes`
- `prune_orphan_graph_edges`

### Outcome enum

- `planned`
- `success`
- `apply_failed`

### Validation rules

- dry-run 僅產生 `outcome="planned"`。
- apply 成功產生 `outcome="success"`。
- 單一 action 失敗產生 `outcome="apply_failed"`，且對應 `FixSkip.reason="apply_failed"`。
- action 不得修改 `manifest.json`，不得刪除 `raw_sources/*` 或 `wiki/pages/*.md`。

## 3. FixSkip

不允許或無法套用的修復。

```python
FixSkip(
    category: FindingCategory,
    reason: FixSkipReason,
    message: str,
    details: dict[str, object] = {},
)
```

### Reason enum

- `requires_manual`
- `unsupported_in_005`
- `manifest_truth_unknown`
- `apply_failed`

### Validation rules

- finding category 不在 fix 許可清單時 MUST 進入 `fixes_skipped[]`。
- `manifest_*` / `wiki_source_mismatch` / `dangling_manifest_entry` 不得自動修 manifest。

## 4. LintSummaryDetail

`trace.steps[kind="lint_summary"].detail` 的唯一合法 shape。

```python
LintSummaryDetail(
    findings: list[Finding],
    severity_counts: dict[Severity, int],
    category_counts: dict[FindingCategory, int],
    fixes_planned: list[FixAction],
    fixes_applied: list[FixAction],
    fixes_skipped: list[FixSkip],
)
```

### Validation rules

- `severity_counts` MUST 永遠含 `error` / `warning` / `info` 三個 key。
- `category_counts` 只列有命中的 category。
- 非 `--fix` 模式下 `fixes_planned` / `fixes_applied` / `fixes_skipped` MUST 皆為空陣列。
- `--fix` dry-run 下 `fixes_planned` 可非空，`fixes_applied` MUST 空。
- `--fix=apply` 下 `fixes_applied` 與 `fixes_skipped` 反映實際 apply 結果；apply 後 MUST 重新 scan 以決定 strict exit code。

## 5. RuntimeSnapshot

lint runner 的 read-only 輸入快照；不對外輸出。

```python
RuntimeSnapshot(
    manifest_entries: dict[str, ManifestEntry],
    raw_source_relpaths: set[str],
    wiki_pages: dict[str, WikiPage],
    wiki_index_slugs: list[str],
    vector_ids: set[str],
    graph_node_ids: set[str],
    graph_edge_ids: set[str],
)
```

### Validation rules

- 建立 snapshot 前 MUST 確認 `/ks/`、`manifest.json`、`wiki/`、`vector/db/` 存在。
- `graph/graph.json` 不存在時視為空 graph；存在但 JSON 損毀時 exit `1 GENERAL`。
- vector store 無法開啟時 exit `1 GENERAL`，不產生 vector findings。

## 6. LintRunMode

內部模式，不輸出為 schema 欄位。

- `lint`
- `strict`
- `fix_plan`
- `fix_apply`
- `strict_fix_apply`

### Exit code rules

- 預設 `lint` / `fix_plan` / `fix_apply` exit `0`，除非 usage / runtime error。
- `strict` 與 `strict_fix_apply` 依 `severity_threshold` 判斷剩餘 findings，命中即 exit `1`。
- usage error exit `2`。
- runtime root / core layer 缺失 exit `66`。
