# Quickstart: Phase 2 階段一 — Office Ingest

**Feature**: 002-phase2-ingest-office
**Audience**: 實作者、QA、檢視本 feature 的 reviewer
**Prerequisite**: 本機已完成 Phase 1（`001-phase1-cli-mvp`）setup，可跑 `uv run ks --help`

## 1. 安裝依賴（新增三個 parser）

```bash
cd /path/to/09-HKS
uv sync   # 會依 pyproject.toml 的新 dep 下載 python-docx / openpyxl / python-pptx
```

若首次 sync 失敗（例如離線環境），確認 `uv.lock` 已 commit 到本分支，並以 `uv sync --offline` 從本機 wheel cache 安裝。

## 2. 生成測試 fixtures

```bash
uv run python tests/fixtures/build_office.py
```

該腳本以 `python-docx` / `openpyxl` / `python-pptx` 程式化生成：

- `tests/fixtures/valid/docx/*.docx`（純文字、含表格、含嵌入圖片 + alt-text）
- `tests/fixtures/valid/xlsx/*.xlsx`（單 sheet、多 sheet、含公式 cached values）
- `tests/fixtures/valid/pptx/*.pptx`（純文字、含 notes、含表格 + 嵌入圖片）
- `tests/fixtures/broken/office/encrypted.pptx`（需 `msoffcrypto-tool` dev-dep；skip 若未安裝）
- `tests/fixtures/broken/office/corrupt.xlsx`（截斷 zip bytes）
- `tests/fixtures/broken/office/empty.docx`（0 byte）
- `tests/fixtures/broken/office/timeout_bomb.docx`（巢狀 1M 段落，觸發 60s 超時）

## 3. 第一次 ingest

```bash
# 設定 /ks/ 根目錄（可用既有 Phase 1 測試目錄或另開）
export KS_ROOT="$(pwd)/.ks-smoke"
rm -rf "$KS_ROOT" && mkdir -p "$KS_ROOT"

# ingest 混合批次
uv run ks ingest tests/fixtures/valid/
```

**預期輸出**：
- exit code `0`
- stdout top-level 符合 Phase 1 `query-response.schema.json`
- `trace.steps[kind="ingest_summary"].detail` 符合 `specs/002-phase2-ingest-office/contracts/ingest-summary-detail.schema.json`
- `detail.files[]` 列出每檔狀態；Office 檔的 `skipped_segments` 正確記錄嵌入素材
- `$KS_ROOT/wiki/pages/` 有對應頁面，xlsx 檔以單頁多 H2 子標題呈現
- `$KS_ROOT/wiki/log.md` 每檔仍是既有 event header，並在對應事件下附 `- skipped_segments: ...` / `- pptx_notes: included`
- `$KS_ROOT/manifest.json` 每 entry 含 `parser_fingerprint`

## 4. 驗證 idempotency

```bash
# 第二次執行相同指令
uv run ks ingest tests/fixtures/valid/
```

**預期**：
- 全部檔案標 `skipped`（`reason="hash_unchanged"`）
- wall-clock 顯著低於首次
- `log.md` 追加新行、但內容型別為 `skipped`

## 5. 驗證 `--pptx-notes` flag

```bash
# 排除 notes 重新 ingest pptx
uv run ks ingest tests/fixtures/valid/pptx/ --pptx-notes=exclude
```

**預期**：
- 先前 `included` 的 pptx 全數觸發 `updated`（因 `parser_fingerprint` 變更）
- `log.md` 對應事件下含 `- pptx_notes: excluded`
- 對該 pptx 做 query → 不命中原 notes 內容

## 6. 驗證降級行為

```bash
uv run ks ingest tests/fixtures/broken/office/
```

**預期**：
- exit code `65`（DATAERR）
- `detail.files[]` 列出各檔失敗原因（`encrypted` / `corrupt` / `timeout` / ...）
- 整批不中斷：同 `broken/office/` 目錄內若含 1 個合法檔（例如空白但合法的 docx），仍被處理
- `/ks/graph/` **不存在**（可用 `ls -la "$KS_ROOT"` 驗）

## 7. 驗證憲法 §I（graph 持續禁止）

```bash
# 全文 grep 禁字
grep -R '"graph"' "$KS_ROOT" && echo "VIOLATION" || echo "OK"

# 目錄禁字
test -d "$KS_ROOT/graph" && echo "VIOLATION" || echo "OK"

# source 程式碼禁字（排除註解 / docstring 的 Phase 2 預告語）
rg -n 'graph' src/hks/ | grep -v '^.*#\|^.*"""' | head
```

## 8. 執行完整測試套

```bash
uv run pytest -q
uv run pytest --cov=hks --cov-report=term-missing
```

**預期**：
- 全數通過
- 新增 parser / 降級情境覆蓋率 ≥ 80%（由 `pyproject.toml [tool.coverage.report] fail_under` 把關）

## 9. 常見 pitfalls

| 現象 | 可能原因 | 處置 |
|---|---|---|
| `ImportError: python-docx` | `uv sync` 未跑 | `uv sync` 或 `uv sync --offline` |
| 某些 xlsx cell 顯示 `0` 而非實際值 | openpyxl 以 `data_only=False` 開啟 | 檢查 pipeline 是否傳 `data_only=True` |
| pptx notes 一律缺失 | CLI flag 被設為 `exclude` 或 env 變數殘留 | `unset HKS_*`，重跑 |
| 60s 超時過於保守 | 實測大型 pptx 接近 60s | `HKS_OFFICE_TIMEOUT_SEC=120` 重試，達成後於 plan.md §13 更新 soft default |
| Windows 執行失敗 | `signal.SIGALRM` 不存在 | 本 spec 明示不支援 Windows；不處理 |

## 10. Historical review notes（僅供審 002 單獨 scope）

以下條目是用來審 `002-phase2-ingest-office` 單獨 feature branch 的 review 要點，不是主分支在完成 `003-phase2-graph-routing` 後的當前 repo 判準。完成 `003` 之後，`src/hks/graph/`、routing 升級、auto write-back 都是刻意存在的，不應再拿本節當成「現在 repo 還缺什麼」的檢核表。

- `pyproject.toml` 在 `002` 單獨 scope 下只應新增 `python-docx` / `openpyxl` / `python-pptx`，不帶 graph / LLM dep
- `002` 單獨 scope 下 `src/hks/graph/` 應不存在
- `002` 單獨 scope 下 `src/hks/routing/rules.py` 不應新增 `llm` 或 `graph` 路徑
- `002` 單獨 scope 下 `src/hks/writeback/` 不應新增自動寫入邏輯
- 契約測試應覆蓋 `contracts/ingest-summary-detail.schema.json` 所有欄位
- `test_query_does_not_reparse_sources` 應涵蓋新格式
- `tests/fixtures/broken/office/` 應至少包含 4 種降級情境（encrypted / corrupt / timeout / empty）
- `wiki/log.md` 附屬欄位應可被 Phase 1 既有 log parser 無痛解析
