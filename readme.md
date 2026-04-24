# README.md

## Hybrid Knowledge System (HKS)

這個 repo 用 specification-first 方式交付 HKS Phase 1 CLI MVP。README 只做導覽；實際安裝、驗收、端到端操作以 `specs/001-phase1-cli-mvp/` 下的文件為準。

## 目前範圍

Phase 1 已落地的 runtime 只有：

* `ks ingest`
* `ks query`
* `ks lint`（stub）
* wiki + vector + rule-based routing + 半自動 write-back

graph 明確延後到 Phase 2；Phase 1 的 JSON、路由與 runtime path 都不允許出現 graph code path。

## Source Of Truth

* 規格：`specs/001-phase1-cli-mvp/spec.md`
* 設計：`specs/001-phase1-cli-mvp/plan.md`
* 安裝 / 測試 / E2E：`specs/001-phase1-cli-mvp/quickstart.md`

## 安裝

不要照 README 猜步驟。直接依 `specs/001-phase1-cli-mvp/quickstart.md` §1–§2 執行：

```bash
uv sync
uv run ks --help
```

## CLI 使用

實際指令、fixture、write-back 情境與 agent 對接範例都在 `specs/001-phase1-cli-mvp/quickstart.md` §3–§9。這裡只保留最小摘要：

```bash
uv run ks ingest <path>
uv run ks query "<question>" [--writeback ask|yes|no]
uv run ks lint
```

`--writeback` 行為：

* `ask`：TTY 詢問，非 TTY 自動 skip
* `yes`：直接回寫
* `no`：永不回寫

exit code 摘要：

* `0`：成功（包含 query 無命中）
* `1`：一般錯誤
* `2`：CLI usage error
* `65`：ingest data error
* `66`：輸入不存在或 `/ks/` 尚未初始化

完整契約見 `specs/001-phase1-cli-mvp/contracts/cli-exit-codes.md`。

## 開發

提交前至少跑：

```bash
uv run pytest --tb=short -q
uv run mypy src/hks
```

## License

MIT
