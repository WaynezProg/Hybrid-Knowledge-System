# Research: HKS Phase 1 MVP — 選型短評

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-23

本文件為 Phase 0 產出。針對 plan.md `Technical Context` 每一項選型，記錄 Decision / Rationale / Alternatives。所有選型須符合憲法 1.1.0：local-first、Python + uv + typer、Phase 1 禁止 graph、CLI-first、domain-agnostic。

---

## 1. Python 版本與依賴管理

**Decision**: Python `>=3.12,<3.13`；`uv` 管理依賴與 venv。

**Rationale**:
- Python 3.12 是目前穩定 LTS 流；3.13 雖已釋出但 `sentence-transformers` / `torch` 在部分平台（尤其 Apple Silicon）之 wheel 仍未完整，3.12 為相容性最佳點。
- 宿主使用 `mise` 管理 runtime，`.mise.toml` 與 `.python-version` 可共存。
- `uv` 相比 `pip + venv + pip-tools` 安裝速度 10×+、自帶鎖定、與 `pyproject.toml` 原生協作；符合全域規範「不 pip install 至 system Python」。

**Alternatives considered**:
- `poetry`：成熟但速度慢、lock 檔膨脹；對 CLI MVP 非必要。
- `hatch`：良好 PEP 517 整合，但依賴管理需要外接 pip-tools；不如 uv 一體化。
- `conda`：過度重（數 GB）、與 `mise` 衝突。

---

## 2. CLI 框架

**Decision**: `typer`。

**Rationale**:
- 憲法 §技術棧明文指定 `typer`；entry point `ks = "hks.cli:app"` 為契約。
- typer 以 type hints 驅動 CLI，與 `mypy strict` 互補。
- 原生支援子指令、`Annotated[str, Option]` 寫法、自動 help；非 TTY 偵測 (`sys.stdout.isatty()`) 與 flag 處理可直接介接。

**Alternatives considered**:
- `click`（typer 底層）：API 較 verbose、無 type hints 驅動。
- `argparse`：過於低階；為 3 個子指令自寫 dispatch 不划算。
- `fire`：inspect 魔法過強，對 agent 穩定介面不利。

---

## 3. PDF Parser

**Decision**: `pypdf`（> 5.x）。

**Rationale**:
- 純 Python，無系統相依（不像 `pdfplumber` / `pdfminer.six` 需要 `cryptography` 等）；macOS/Linux offline 可用。
- 足以應付 Phase 1 驗收（一般文字 PDF）；複雜排版 / 表格 / OCR 明確於 Phase 2 / 3 再處理。
- 壞檔容易偵測：`pypdf.errors.PdfReadError` 可包裝為 exit `65`。
- 檔案大小上限由應用層 `HKS_MAX_FILE_MB` 檢查，不依 pypdf 記憶體行為。

**Alternatives considered**:
- `pdfplumber`：表格抽取佳，但相依 `pdfminer.six`；Phase 1 不需要表格。
- `pymupdf (fitz)`：速度快，但 AGPL license 與 MIT 專案衝突。
- `docling` / `marker`：品質最好，但需要 GPU + 模型下載 > 數 GB，違反 local-first 最低門檻。Phase 2 討論。

---

## 4. Markdown Parser

**Decision**: `markdown-it-py`。

**Rationale**:
- CommonMark-compliant、可擴充至 MyST（Phase 2 可能想解析 frontmatter / cross-link），升級無痛。
- 純 Python、pypi 穩定。
- 本階段實際用途是從 md 抽取標題 / 段落結構供 wiki 生成與 chunking，不需 render。

**Alternatives considered**:
- `mistune`：快但 extension 生態較弱。
- `python-markdown`：老牌、plugin 多，但 CommonMark 合規性不如 markdown-it-py。

---

## 5. Embedding 模型

**Decision**: `sentence-transformers` + `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。

**Rationale**:
- 支援 zh-TW + 英語（與 routing_rules.yaml 雙語策略一致）。
- 模型大小 ~118 MB、384-dim，CPU 可跑；commodity laptop 可達 p95 < 3s 查詢目標（前提是 ingest 完畢，query 時只做一次 query-embedding + chroma nearest）。
- 首次啟動下載並快取 `~/.cache/huggingface`，後續離線可用。
- 環境變數 `HKS_EMBEDDING_MODEL` 覆寫；企業離線部署可預先 bundle 本機路徑。

**Alternatives considered**:
- `BGE-M3` / `bge-small-zh`：中文表現更佳，但英語場景品質下降；單語選一違反多語定位。
- `text-embedding-3-small`（OpenAI）：需連網，違反 local-first。
- `fastembed`：ONNX 輕量，但模型選擇少、非 zh 語料微調；保留為 Phase 2 效能替代選項。

---

## 6. Vector DB

**Decision**: `chromadb`（PersistentClient，檔案型）。

**Rationale**:
- 純 Python 檔案儲存，落地於 `/ks/vector/db/`，符合 [docs/main.md §8](../../docs/main.md) 資料結構。
- 實作上以 `chromadb.PersistentClient` 搭配自管 embedding：`VectorStore` 先經 `TextModelBackend(HKS_EMBEDDING_MODEL)` 產生向量，再以 `collection.upsert(..., embeddings=...)` 寫入。這讓 runtime 可在真實 `sentence-transformers` 與 `HKS_EMBEDDING_MODEL=simple` deterministic fallback 間切換，不把模型載入策略綁死在 Chroma adapter。
- Collection 層級可做 metadata filter（為將來 `source_path` filter 預留）。
- **Vector-only**：不提供 graph / relation 能力，符合憲法 §I 的 Phase 1 禁止 graph。

**Alternatives considered**:
- `qdrant`（embedded mode）：品質好，但檔案格式綁定；輕量 CLI 場景 chroma 足矣。
- `lancedb`：Arrow-native、壓縮佳，但 API 變動頻繁、zh-TW 字元在 FTS 時有 bug（2026-04 測）。
- `sqlite-vss` / `duckdb` + vss：最小依賴，但 distance metric 限制多、沒現成 embedding 整合；增加 glue code。
- `faiss`：快但僅 index、無 metadata store；需自己搭索引層，增加複雜度。

---

## 7. YAML 讀取

**Decision**: `ruamel.yaml`。

**Rationale**:
- 保留註解與 key 順序，`routing_rules.yaml` 由人類維護時不會被程式寫回洗掉。
- 雖僅讀取，此選擇為 Phase 2 自動新增規則（若需要）預留無痛升級路徑。

**Alternatives considered**:
- `pyyaml`：標準，但寫回會丟註解、重排 key；Phase 2 痛點。
- `strictyaml`：過於嚴格、語法受限、生態小。

---

## 8. Slugify

**Decision**: `python-slugify`（含 `text-unidecode`）。

**Rationale**:
- 原生支援 unicode → ASCII 音譯（中文檔名 → pinyin 近似），避免 `專案A.pdf` 直接變成空字串。
- 衝突 `-<n>` 後綴由 storage 層自行處理（本庫不做 state），配合 manifest。

**Alternatives considered**:
- 手寫 `unicodedata.normalize + re.sub`：可行，但 unicode 邊界條件多，音譯規則自寫易錯。
- `awesome-slugify`：已停維護（上次 release 2018）。

---

## 9. JSON Schema 驗證

**Decision**: `jsonschema`（Draft 2020-12）。

**Rationale**:
- Python 標配；可在 `cli.py` 最後一道出口 `validate()` 全輸出，runtime assert 憲法 §II 合約。
- 契約測試（`tests/contract/test_json_schema.py`）與 runtime assert 共用同一份 schema file，單一事實來源。
- 可在 PR 中以 `jsonschema-cli` 離線檢查 `contracts/query-response.schema.json` 本身合規。

**Alternatives considered**:
- `pydantic v2`：優秀 but 雙軌（dataclass + schema）會發散；選擇 `core/schema.py` 用 dataclass + `jsonschema` 單軌驗證。
- `fastjsonschema`：快但錯誤訊息可讀性差；CLI 人類使用者看錯誤需要好訊息。

---

## 10. 測試與覆蓋率

**Decision**: `pytest` + `pytest-cov`，覆蓋率 ≥ 80% 於 `pyproject.toml [tool.coverage.report] fail_under = 80`。

**Rationale**:
- `pytest` 生態成熟；`pytest-cov` 與 CI 一鍵整合。
- 覆蓋率門檻以 pyproject 強制，PR 違反即 test fail，不仰賴 reviewer 記憶。
- 覆蓋率豁免範圍：`hks/__init__.py`、`hks/cli.py` 的 typer boilerplate（以 `.coveragerc` 或 `[tool.coverage.run] omit` 指定）。

**Alternatives considered**:
- `unittest`：維護性 / 擴充性不如 pytest。
- `nox`：多 env 矩陣用途；本 MVP 單 env 足矣，留 Phase 3。

---

## 11. Lint / Format / Type check

**Decision**: `ruff` + `mypy --strict`。

**Rationale**:
- `ruff`：一次取代 black + isort + flake8 + pyupgrade；速度極快，預設規則集足夠 MVP。
- `mypy --strict` 於 `[tool.mypy] strict = true`：與 typer type hints 協作；第三方無 stub 者以 `ignore_missing_imports` 逐庫寬鬆。
- Phase 2 可補 `pre-commit` hook，本階段先靠 CI。

**Alternatives considered**:
- `black` + `isort` + `flake8`：三個工具、維護成本高；被 ruff 完全取代。
- `pyright`：速度更快，但 Python-only 專案使用 mypy 生態工具更順。

---

## 12. 檔案大小與 Chunking

**Decision**:
- 單檔 200 MB 硬上限（超過即 exit `65`），由環境變數 `HKS_MAX_FILE_MB` 覆寫。
- Chunking：`512 token / 64 token overlap`，以 MiniLM tokenizer (`AutoTokenizer`) 計數。

**Rationale**:
- 200 MB 覆蓋 99% 個人知識文件（PDF）；超過此大小通常是掃描 / 圖檔，本階段非目標（Phase 3 OCR）。
- MiniLM 最大 context 約 512 tokens；超出即截斷，不如明確 chunking。64 token overlap 在多數 RAG 基準中為平衡點（太小丟 context、太大放大重複與儲存）。

**Alternatives considered**:
- 固定字元切（例如 1500 chars）：簡單但對 token 不精確，浪費 MiniLM capacity。
- 句子邊界切（`sentence-splitter`）：對中文斷句品質不一；Phase 2 可升級。

---

## 13. Package Layout（src-layout vs flat）

**Decision**: `src/hks/` src-layout。

**Rationale**:
- src-layout 強迫測試使用「已安裝的 package」而非 cwd import，避免 `PYTHONPATH` 污染造成 CI 與本機行為不一致。
- `typer` 配合 entry point `ks = "hks.cli:app"` 需 `hks` 為可安裝 package；src-layout 在 `pyproject.toml` 搭 `hatchling` / `setuptools` 均可。
- 與未來 Phase 2 新增套件並列時，src-layout 自然 scale。

**Alternatives considered**:
- Flat layout（`hks/` 在 repo root）：歷史常見但有 import 黑魔法風險。
- Namespace package：對單一 package 過度工程。

---

## 14. Lock 檔與 `/ks/` 目錄的並發控制

**Decision**: Phase 1 採「檔案鎖」`/ks/.lock`，由 `core/paths.py` 的 `acquire_lock()` 以 `fcntl.flock()`（POSIX）實作；偵測到現有鎖即 exit `1`。

**Rationale**:
- Phase 1 假設單使用者（spec Assumption）；鎖檔防止意外並發 ingest 撕裂 manifest。
- `fcntl` 為 Python stdlib，無相依。
- Phase 2 多 agent 共用時再擴充至 advisory lock 或 SQLite `BEGIN IMMEDIATE`。

**Alternatives considered**:
- `filelock` pypi 套件：功能相同、外部依賴。
- 不鎖：並發容易造成 manifest JSON 寫入競爭。

---

## 15. 待決事項（轉交 Phase 2 設計或實作時 spike）

以下為 plan 階段有意識延後、非本 feature 阻塞項：

- **PDF 表格 / 圖片處理**：Phase 2 / 3；pypdf 對表格回傳為散亂文字，Phase 1 容忍此降級。
- **query 對相同問句的 cache**：Phase 1 不 cache；p95 < 3s 目標即使無 cache 也能達成（測試會驗證）。
- **wiki 頁面跨檔聚合**：Phase 1 一來源一頁；跨檔主題聚合屬 Phase 2 graph / LLM routing 配套。
- **多語言擴充**：Phase 1 僅 zh-TW + 英；其他語言待需求出現再加 `routing_rules.yaml` 關鍵字表。

以上各項不影響 Phase 1 驗收，不列入 Complexity Tracking。
