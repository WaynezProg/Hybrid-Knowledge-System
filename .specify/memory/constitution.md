<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.1.0
Type: MINOR — extend §II (Stable Output Contract) with CLI Exit Codes sub-contract

Modified principles:
  - §II Stable Output Contract — 新增「CLI Exit Codes（附屬契約）」，規範 agent 可依賴的 exit code 集合（BSD sysexits 子集）
Added sections: N/A (extension of §II)
Removed sections: N/A

Templates scanned for alignment:
  - .specify/templates/plan-template.md     ✅ compatible
  - .specify/templates/spec-template.md     ✅ compatible
  - .specify/templates/tasks-template.md    ✅ compatible
  - .specify/templates/checklist-template.md ✅ compatible
  - .specify/templates/agent-file-template.md ✅ compatible
  - README.md / docs/main.md / docs/PRD.md / CLAUDE.md  ✅ 已對齊；docs/main.md §5 / §8 同步擴充 route/source 語意與 data 結構

Deferred TODOs: none
-->

# Hybrid Knowledge System (HKS) Constitution

本憲法為 HKS 專案所有規格、計畫、任務與實作的最高準則。三份設計文件（`readme.md`、`docs/main.md`、`docs/PRD.md`）若敘述衝突，以 [docs/main.md](../../docs/main.md) 為準；本憲法若與任何設計文件衝突，以本憲法為準。

## Core Principles

### I. Phase Discipline（分階段實作，嚴禁跳做）

開發嚴格按 Phase 1 → Phase 2 → Phase 3 順序推進，**不得跨 Phase 借用功能**。

- **Phase 1 (MVP)**：CLI (`ks`) + wiki + vector + rule-based routing（**僅 wiki / vector 兩路**）+ ingest(txt / md / pdf) + 半自動 write-back + `ks lint` stub。
- **Phase 2**：新增 graph + LLM-based routing + 全自動 write-back + ingest(docx / xlsx / pptx)。
- **Phase 3**：`lint` 實作 + 多 agent + API / MCP adapter + ingest(png / jpg，OCR / VLM)。

**強制規則**：
- Phase 1 程式碼中 **MUST NOT** 出現 graph 構造、graph 查詢、LLM-based routing 或自動 write-back 邏輯。發現即視為違反憲法，PR 須退回。
- 跨 Phase 功能若有前置鋪墊需求（例如 Phase 1 需預留 graph 介面），必須於 plan.md 的 `Complexity Tracking` 明確記錄豁免理由。
- 三份設計文件敘述不一致時，以 [docs/main.md](../../docs/main.md) 為準；變更 Phase 邊界屬於 MAJOR 憲法修訂。

**理由**：防止 MVP 膨脹、控制不可逆設計債；Phase 分野是 routing、ingestion、write-back 三條主動脈的演進契約。

### II. Stable Output Contract（CLI 輸出為對外 API）

`ks` 指令輸出 JSON schema 為對外穩定介面，供 agent（OpenClaw / Codex / Claude Code / Qwen Code）解析。

Schema（Phase 1~3 通用）：

```json
{
  "answer": "string",
  "source": ["wiki", "graph", "vector"],
  "confidence": 0.0,
  "trace": {
    "route": "wiki|graph|vector",
    "steps": []
  }
}
```

**強制規則**：
- 欄位名稱、型別、巢狀結構變更 **MUST** 視為 breaking change，需 MAJOR 版本升級並於 release notes 明示。
- 新增欄位屬 MINOR；欄位值域擴充（例如 `route` 允許新值）屬 MINOR，前提是現有 agent 解析不會崩潰。
- Phase 1 因無 graph，`source` 陣列 **MUST NOT** 出現 `"graph"`；`trace.route` **MUST NOT** 為 `"graph"`。
- 任何需求若要改 schema，必須於 spec.md 的 `Requirements` 段落明確標示 schema 變更與影響面。

**Route / Source 語意**：
- `trace.route` 表示最終採用的主要路徑；`source` 表示實際取用到的知識層（可為複數）。Phase 1 組合表詳見 [docs/main.md §5.4](../../docs/main.md)。
- fallback 過程（rule 判定、wiki 未命中切換 vector、merge 等）**MUST** 於 `trace.steps` 留下可追溯紀錄。

**CLI Exit Codes（附屬契約）**：

agent 依 exit code 分支，故為對外介面的一部分。採 BSD `sysexits.h` 子集：

| Code | 名稱 | 使用情境 |
|---|---|---|
| `0` | OK | 指令成功（含 query 有效命中與 query 無命中但流程正常） |
| `1` | GENERAL | 未分類執行錯誤（保底） |
| `2` | USAGE | 指令參數 / flag 錯誤 |
| `65` | DATAERR | ingest 來源解析失敗（壞檔、格式不支援、編碼錯） |
| `66` | NOINPUT | 指令要求的資源不存在（例如 `ks query` 前 `/ks/` 未初始化、ingest 目標路徑不存在） |

**強制規則**：
- 新增 exit code **MUST** 走 MINOR 版本升級；改變既有 code 的語意屬 MAJOR（breaking）。
- `ks query` 無命中 **MUST NOT** 以非零 exit code 回報；語意由 JSON body（`source=[]`、`answer` 說明未命中）承擔，agent 仍能解析。
- 發生錯誤時，若可行 **SHOULD** 同時輸出符合 §II schema 的 JSON（`answer` 填錯誤說明），以降低 agent 解析特例。

**理由**：HKS 的價值在於可被多 agent 共用；介面一旦不穩，整個 agent 生態會崩。exit code 是 JSON 之外 agent 唯一的第二通訊管道，必須與 schema 同等穩定。

### III. CLI-First & Domain-Agnostic（僅 CLI、不綁領域）

系統唯一入口為 `ks` CLI；不預設任何垂直領域（程式碼、法律、醫療等）。

**強制規則**：
- Phase 1~2 **MUST NOT** 實作：UI（Web / Desktop / TUI）、多使用者 / RBAC、雲端部署、Microservice、MCP adapter、非文字素材處理（影片 / 音訊）。
- 任何 ingestion、routing、write-back 邏輯 **MUST NOT** hard-code 特定領域詞彙或規則；領域特化須透過配置而非程式碼。
- 新增功能若需要上述任何非目標能力，**MUST** 退回需求並說明與 Non-goals 衝突。

**理由**：範圍一旦擴散，CLI-first 與三層同步的設計假設會失效。

### IV. Ingest-Time Organization（寫入時整理，查詢時不重算）

Ingestion pipeline 必須在寫入階段即完成 `parse → normalize → extract → update`，同時同步 wiki / graph(Phase 2+) / vector 三層。查詢時**只讀取已整理好的結構**，不得臨時拼湊或 re-chunk。

**強制規則**：
- 修改 ingestion 任一階段 **MUST** 同時審視三層同步行為；plan.md 須列出受影響的層與同步策略。
- 查詢路徑（`ks query`）**MUST NOT** 觸發重新 parse / 重新 embedding / 重新抽取；此類需求屬 ingestion 邏輯，須走 `ks ingest`。
- 三層之間的一致性由 ingestion 保證；若 ingestion 中斷，**MUST** 能識別並回報不一致狀態（例如 vector 已建、wiki 未更新）。

**理由**：此為 HKS 相對傳統 RAG 的核心差異；破壞此原則等於退化為普通 RAG。

### V. Write-back Safety（Phase 1 半自動、禁止自動寫入）

Write-back（將查詢結果回寫 wiki）在 Phase 1 **MUST** 為半自動：每次 query 結束後由使用者明確確認，確認後更新 `wiki/index.md` 並於 `wiki/log.md` 追加紀錄。

**強制規則**：
- Phase 1 **MUST NOT** 存在任何「高 confidence 自動回寫」或「背景靜默寫入」邏輯。
- Phase 2 始得開放全自動 write-back，且必須提供使用者關閉開關（opt-out）。
- 任何回寫操作 **MUST** 於 `trace.steps` 留下可追溯紀錄。

**理由**：知識污染不可逆；Phase 1 ingestion 與 routing 尚未驗證，自動寫入會放大錯誤並失去使用者信任。

## Technology Stack & Operational Constraints

**Language & Runtime**：
- 實作語言：Python（以 `pyproject.toml` 宣告 `requires-python`，Phase 1 採用當前 LTS 穩定版）。
- 依賴管理：`uv`（禁用 `pip install` 直接寫入 system Python）。
- CLI 框架：`typer`。Entry point **MUST** 宣告為 `ks = "<package>.cli:app"`。

**Data Layout**（專案根目錄下）：

```
/ks
  /raw_sources          # immutable 原始檔
  /wiki
    index.md
    log.md
  /graph/graph.json     # Phase 2 才建立；Phase 1 禁止寫入
  /vector/db/
```

**Local-First**：
- 所有 Phase 1~2 核心路徑 **MUST** 在無網路環境可執行（embedding / LLM 可用本地模型）；雲端服務僅作為可選加速，不得為必要相依。
- 平均本地查詢延遲目標 `< 3s`（PRD §6）。

**禁用技術**：
- UI 框架（Web / Desktop / TUI）在 Phase 1~2 **MUST NOT** 引入。
- 任何 graph 資料庫（neo4j、nebula 等）在 Phase 1 **MUST NOT** 出現於 dependencies。

## Development Workflow & Quality Gates

**Testing Gate**：
- PR 合併前 **MUST** 執行 `uv run pytest` 且全數通過。
- Ingestion、routing、JSON schema 三類變更 **MUST** 附帶對應測試。
- Hook 失敗不得以 `--no-verify` 繞過；應修正根因後重新提交。

**Plan / Spec Gate**：
- 每個 feature **MUST** 具備 `spec.md`、`plan.md`、`tasks.md`（依 speckit 流程產出）。
- `plan.md` 的 `Constitution Check` 段落必須逐一對照本憲法五項原則，違反者需於 `Complexity Tracking` 明列豁免與替代方案。
- 變更 CLI JSON schema 的 PR **MUST** 於描述標示 `BREAKING:` 並連結此憲法 §II。

**Language Discipline**：
- 文件、commit message、PR 描述使用 **Traditional Chinese (zh-TW)**。
- 程式碼、識別字、型別、技術術語使用英文；簡體中文（zh-CN）禁用。

**Review Expectations**：
- 審查者 **MUST** 將本憲法視為強制檢核清單；違反 §I（Phase Discipline）或 §II（Stable Output Contract）的 PR 應直接退回，不進入技術細節討論。
- 豁免僅能由憲法修訂或 plan.md 明文記錄之 Complexity Tracking 授權。

## Governance

**憲法優先順序**：本憲法凌駕 README、PRD、CLAUDE.md 之上。設計文件可被憲法約束，不可反向覆寫憲法。

**修訂流程（Amendment Procedure）**：
1. 任一原則之新增、移除或重新定義 **MUST** 經 PR 提出，說明動機、影響面、對既有 spec / plan / tasks 的 migration 計畫。
2. PR 描述 **MUST** 附上版本升級類型（MAJOR / MINOR / PATCH）與理由。
3. 合併前 **MUST** 更新本文件頂端的 Sync Impact Report，並確認 `.specify/templates/*` 已同步對齊。

**版本政策（Semantic Versioning）**：
- **MAJOR**：原則或治理規則的不相容變更、原則移除、Phase 邊界調整、CLI JSON schema 破壞性變更。
- **MINOR**：新增原則或章節、大幅擴充既有原則的規範力。
- **PATCH**：措辭釐清、錯字修正、不改變語意的精煉。

**合規審查（Compliance Review）**：
- 所有 PR 審查 **MUST** 驗證合規；不合規項目必須於 `Complexity Tracking` 具名豁免或退回。
- Runtime 操作指引參照 [CLAUDE.md](../../CLAUDE.md)；該檔為 agent 行為指南，須與本憲法保持一致，若衝突以本憲法為準並同步更新 CLAUDE.md。

**Version**: 1.1.0 | **Ratified**: 2026-04-23 | **Last Amended**: 2026-04-23
