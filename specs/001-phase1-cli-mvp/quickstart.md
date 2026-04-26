# Quickstart: HKS Phase 1 MVP

**Audience**: 新 contributor 或跑 agent 對接測試的工程師
**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Prereq**: 宿主已安裝 `mise` 與 `uv`（全域慣例），Python 版本需符 `>=3.12,<3.13`。

---

## 1. 取得程式碼並準備 Python 環境

```bash
git clone https://github.com/WaynezProg/Hybrid-Knowledge-System.git hks && cd hks
git checkout 001-phase1-cli-mvp       # 本 feature branch

# mise 自動讀取 .mise.toml → 選 Python 3.12
mise install                          # 若未安裝 3.12
mise use python@3.12                  # 可選；.mise.toml 已指定

# uv 建立 venv 並同步依賴
uv sync                               # 讀 pyproject.toml + uv.lock
```

驗證:

```bash
uv run python -c "import sys; print(sys.version)"   # 期望 3.12.x
uv run ks --help                                    # 看到 ingest / query / lint 指令
```

---

## 2. 跑測試

```bash
uv run pytest                          # 全測試
uv run pytest -m unit                  # 僅單元
uv run pytest -m contract              # JSON schema + exit code 契約測試
uv run pytest --cov=hks --cov-report=term-missing    # 覆蓋率（門檻 80% 由 pyproject 把關）
```

Lint / format / type:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/hks
```

---

## 3. 第一次 ingest 與 query（冒煙測試）

```bash
# 複製一份工作語料，避免後續 idempotency 節直接修改 repo fixture
DOCS_DIR=$(mktemp -d /tmp/hks-phase1-docs.XXXXXX)
cp -R tests/fixtures/valid/. "$DOCS_DIR"

# 若當前環境無外網，先看 §7 設定 HKS_EMBEDDING_MODEL，再回來執行
uv run ks ingest "$DOCS_DIR"

# 結果會建立在 cwd 下的 /ks/（可用 KS_ROOT 環境變數覆寫）
ls ks/
# raw_sources/  wiki/  vector/  manifest.json

# 看 wiki index
cat ks/wiki/index.md

# query
uv run ks query "這批文件的重點是什麼"             # 預期走 wiki
uv run ks query "clause 3.2 text"                 # 預期走 vector
uv run ks query "A 專案延遲會影響哪些系統"         # 預期走 vector，附 Phase 2 附註
uv run ks query "明天吃什麼"                       # 預期無命中，仍 exit 0
```

每筆 query 的 stdout 是單一 JSON object。用 `jq` 檢視:

```bash
uv run ks query "這批文件的重點是什麼" | jq .
```

驗證輸出結構:

```bash
uv run ks query "..." | uv run python -c "
import sys, json, jsonschema, pathlib
schema = json.loads(pathlib.Path('specs/001-phase1-cli-mvp/contracts/query-response.schema.json').read_text())
jsonschema.validate(json.load(sys.stdin), schema)
print('schema ok')
"
```

---

## 4. Write-back 行為驗證

```bash
# TTY 互動（會問 y/n）
uv run ks query "summary Atlas"                     # 回 y 會寫入 wiki/pages/ 與 log.md

# 非 TTY 自動跳過
uv run ks query "summary Atlas" | cat               # trace.steps 有 writeback=skip-non-tty

# Flag 覆寫
uv run ks query --writeback=yes "summary Atlas" | cat  # 不問直接寫
uv run ks query --writeback=no  "summary Atlas"        # TTY 下也不寫
```

寫入後:

```bash
tail -n 20 ks/wiki/log.md      # 看 append 紀錄
ls ks/wiki/pages/               # 看新增頁面
```

---

## 5. Idempotency 驗證

```bash
time uv run ks ingest "$DOCS_DIR"    # 首次：建立 manifest + artifacts
time uv run ks ingest "$DOCS_DIR"    # 再跑：應顯示 "skipped (hash unchanged)"，總時間 < 首次 50%
```

修改一份 md → 再 ingest → 驗證只有該檔更新:

```bash
MD_FIXTURE=$(find "$DOCS_DIR" -name '*.md' | head -n 1)
echo "\n\n追加內容" >> "$MD_FIXTURE"
uv run ks ingest "$DOCS_DIR"
# 預期: 9 skipped, 1 updated
grep "\"$(basename "$MD_FIXTURE")\"" ks/manifest.json
```

---

## 6. Exit code 契約驗證（手動）

```bash
uv run ks query "anything"; echo $?                      # 0（有或無命中皆 0）
uv run ks ingest /tmp/does-not-exist; echo $?            # 66
uv run ks ingest tests/fixtures/broken/broken.pdf; echo $?  # 65
uv run ks query "..." --unknown-flag; echo $?            # 2
```

所有 exit code 行為見 [contracts/cli-exit-codes.md](./contracts/cli-exit-codes.md)。

---

## 7. 離線 / 自訂 embedding 模型

預設首次啟動會自動下載 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（~118 MB）至 `~/.cache/huggingface/`。若當前 shell 沒外網，先把 `HKS_EMBEDDING_MODEL` 指到本機模型目錄，再回去跑 §3–§6。

若需要預下載或指向本機路徑:

```bash
# 預先下載
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# 指向本機快取或 bundle 好的模型目錄
export HKS_EMBEDDING_MODEL=/path/to/local/model
uv run ks ingest ...
```

只做 deterministic smoke test / CI 時，也可改設：

```bash
export HKS_EMBEDDING_MODEL=simple
```

---

## 8. 常用環境變數

| 變數 | 預設 | 用途 |
|---|---|---|
| `KS_ROOT` | `./ks` | `/ks/` 資料根目錄 |
| `HKS_EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 覆寫 embedding 模型 |
| `HKS_MAX_FILE_MB` | `200` | 單檔 ingest 上限 |
| `HKS_ROUTING_RULES` | 未設 | 覆寫 routing_rules.yaml 路徑 |
| `NO_COLOR` | 未設 | 停用 stderr 彩色 |

---

## 9. 對 agent 的最小對接範例

任何 agent（OpenClaw / Codex / Claude Code / Qwen Code）皆可:

```bash
# agent 取得結構化答案
ANSWER_JSON=$(uv run ks query "summary Atlas" --writeback=no)
echo "$ANSWER_JSON" | jq -r '.answer'
ROUTE=$(echo "$ANSWER_JSON" | jq -r '.trace.route')

# 檢查 exit code
if ! uv run ks ingest "$INPUT_DIR"; then
  case $? in
    65) echo "ingest data error" ;;
    66) echo "input not found" ;;
    *)  echo "other error" ;;
  esac
fi
```

---

## 10. 常見問題

- **`uv sync` 在無網路時失敗**：先同步一次產生 lock；或以 `uv pip install --offline` 搭預下載 wheels。
- **`ks query` 首次很慢**：首次執行會載入 embedding 模型（約 5–10 秒，依機器）。後續查詢 p95 < 3s。
- **中文 query 走 vector 時命中率低**：先檢查 chunking 與 vector lookup（`uv run pytest tests/unit/ingest/test_normalizer.py tests/integration/test_query_flows.py`）。若語料為掃描 PDF，Phase 1 不支援（Phase 3 OCR 再處理）。
- **wiki/index.md 與 pages/ 不一致**：執行 `uv run ks ingest --prune`（Phase 1 預設不啟用 prune）或刪 `/ks/` 重新 ingest。
