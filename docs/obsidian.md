# Obsidian-friendly Wiki

HKS 產生的 `$KS_ROOT/wiki/` 是一般 Markdown 目錄，可以直接用 Obsidian 開成 vault 閱讀。這只是閱讀與人工補充筆記的介面；HKS 的 authoritative source 仍是 `raw_sources/` 與 `manifest.json`。

## 開啟方式

先建立或更新一個 HKS runtime：

```bash
mkdir -p .hks-runs/demo
export KS_ROOT="$PWD/.hks-runs/demo/ks"
export HKS_EMBEDDING_MODEL=simple
uv run ks ingest tests/fixtures/valid
```

然後在 Obsidian 選擇 `Open folder as vault`，路徑選：

```text
$KS_ROOT/wiki
```

開啟後可以從 `index.md` 進入各個 `pages/*.md`。HKS 產生的 index 使用標準 Markdown relative links，例如：

```markdown
- [Project Atlas](pages/project-atlas.md)
```

這種格式不依賴 Obsidian plugin，也不需要 Obsidian API。

## HKS 會寫入什麼

`ks ingest` 會在 `$KS_ROOT/wiki/` 產生：

- `index.md`：所有 wiki pages 的入口索引
- `log.md`：ingest、write-back、lint fix、wiki synthesis 等事件紀錄
- `pages/*.md`：每個 source 或 applied wiki synthesis 對應的 Markdown page

`pages/*.md` 會包含 YAML-readable frontmatter，常見欄位包含 `slug`、`title`、`summary`、`source`、`origin`、`updated_at`。Obsidian 可以顯示這些 properties；HKS 也會用這些欄位做 lint、lineage 與 source reconciliation。

## 限制與建議

`origin=ingest` 的頁面是由 raw source 產生；同一份 source 重新 `ks ingest` 時，這些頁面會被覆蓋。

Obsidian 內手動修改 `$KS_ROOT/wiki/pages/*.md` 不會更新 `graph/graph.json`、`vector/db/` 或 `page_trees/`。如果要更新檢索內容，請修改原始檔後重跑 `ks ingest`，或走 HKS 的 LLM classification / wiki synthesis workflow。

人工筆記不要直接混進 HKS 管理的 ingest page。建議使用：

- `manual-*.md`：放在 `wiki/pages/` 時用明確 prefix 標示人工頁
- `manual/` 或 `notes/`：放在 `$KS_ROOT/wiki/` 下的獨立資料夾
- 獨立 Obsidian vault：如果人工知識會長期維護，請把 HKS wiki 當 read-only reference

人工筆記可連到 HKS pages，例如 `[Project Atlas](../pages/project-atlas.md)`；但 HKS 不會把這些人工連結視為 graph/vector/page_tree 的 authoritative input。

## 邊界

HKS 不提供 Obsidian plugin，不讀 Obsidian vault metadata，也不使用 Obsidian API。`$KS_ROOT/wiki/` 的設計目標是讓現有 Markdown artifacts 能被 Obsidian 直接瀏覽；資料同步、檢索與 provenance 仍由 HKS runtime 管理。
