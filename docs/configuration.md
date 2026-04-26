# HKS Configuration Guide

這份文件教你建立本機設定檔、填入可調參數、啟用設定，並確認 agent / CLI 真的讀到同一套 runtime。

## 設定檔種類

建議使用 YAML：

```bash
cp config/hks.yaml.example config/hks.yaml
$EDITOR config/hks.yaml
```

也可以使用 JSON：

```bash
cp config/hks.json.example config/hks.json
$EDITOR config/hks.json
```

`config/hks.yaml`、`config/hks.json`、`config/hks.env` 都是本機設定，已被 `.gitignore` 排除。不要提交真實 API key。

讀取優先序：

```text
process env > config/hks.env > config/hks.yaml 或 config/hks.json > default
```

`config/hks.env` 只建議用在需要 shell-style override 時；一般設定請用 YAML。

## 最小 OpenAI 設定

`config/hks.yaml` 至少填這幾段：

```yaml
runtime:
  ks_root: "${HKS_REPO_ROOT}/.hks-runs/openai/ks"
  workspace_registry: "${HKS_REPO_ROOT}/.hks-runs/workspaces.json"

embedding:
  model: "openai:text-embedding-3-small"
  openai:
    api_key: "sk-REPLACE_ME"
    endpoint: "https://api.openai.com/v1/embeddings"
    dimensions: 1536
    timeout_seconds: 60
    batch_size: 128
    max_batch_tokens: 250000
```

OpenAI embedding 會建立新的 vector DB。不要把已用 `simple` 或 sentence-transformers 建好的 `$KS_ROOT/vector/db` 直接改成 OpenAI 查，會發生 embedding dimension mismatch。

## 常用可調值

```yaml
routing:
  model: "simple"
  rules_path: null

writeback:
  auto_threshold: 0.75

ingest:
  max_file_mb: 200
  office:
    timeout_sec: 60
    max_file_mb: 200
  image:
    timeout_sec: 30
    max_file_mb: 20
    max_pixels: 100000000
  ocr:
    langs:
      - eng
      - chi_tra

llm:
  provider: "fake"
  model: "fake-llm-extractor-v1"
  network_opt_in: false
  providers:
    openai:
      api_key: "sk-REPLACE_ME"
      endpoint: null
```

`routing.model` 會真的決定 routing semantic scoring 使用的 embedding backend。可用值包含：

- `simple`：本機 deterministic backend，無 API cost，適合 smoke test / CI。
- `openai:text-embedding-3-small`：使用 OpenAI Embeddings API 做 routing scoring。
- sentence-transformers model id 或本機模型路徑：使用本機 sentence-transformers backend。

`embedding.openai.batch_size` 與 `embedding.openai.max_batch_tokens` 控制單次 OpenAI embeddings request 的上限；大型資料夾 ingest 時會自動分批，避免超過 OpenAI per-request token limit。

這些欄位會對應到既有 env contract，例如 `HKS_MAX_FILE_MB`、`HKS_IMAGE_TIMEOUT_SEC`、`HKS_WRITEBACK_AUTO_THRESHOLD`、`HKS_LLM_PROVIDER_OPENAI_API_KEY`。

## 啟用設定

所有 agent session 先跑：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
```

這會讀取：

- `config/hks.env`
- `config/hks.yaml` 或 `config/hks.json`
- `.hks-runs/shared-runtime.env`

如果要固定 shared runtime 指標，可建立：

```bash
mkdir -p .hks-runs
cat > .hks-runs/shared-runtime.env <<'EOF'
export KS_ROOT="$HKS_REPO_ROOT/.hks-runs/openai/ks"
export HKS_WORKSPACE_REGISTRY="$HKS_REPO_ROOT/.hks-runs/workspaces.json"
EOF
```

## 驗證設定

看 YAML / JSON 會匯出哪些 env：

```bash
uv run python -m hks.core.config --shell
```

看目前 active runtime：

```bash
sh skill/hks-knowledge-system/config/discover-runtime.sh
```

確認 CLI 讀到設定：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
echo "$KS_ROOT"
echo "$HKS_EMBEDDING_MODEL"
echo "$HKS_OPENAI_EMBEDDING_DIMENSIONS"
```

第一次使用 OpenAI runtime 要重新 ingest：

```bash
. skill/hks-knowledge-system/config/shared-runtime.sh
uv run ks ingest <source-dir>
uv run ks workspace register openai --ks-root "$KS_ROOT" --label "OpenAI" --force
uv run ks workspace query openai "目前有哪些資料？" --writeback=no
```

## JSON 等價範例

```json
{
  "runtime": {
    "ks_root": "${HKS_REPO_ROOT}/.hks-runs/openai/ks",
    "workspace_registry": "${HKS_REPO_ROOT}/.hks-runs/workspaces.json"
  },
  "embedding": {
    "model": "openai:text-embedding-3-small",
    "openai": {
      "api_key": "sk-REPLACE_ME",
      "endpoint": "https://api.openai.com/v1/embeddings",
      "dimensions": 1536,
      "timeout_seconds": 60
    }
  }
}
```

## Troubleshooting

- `OPENAI_EMBEDDING_CREDENTIAL_MISSING`：`embedding.openai.api_key` 沒填，或 process env / `config/hks.env` 覆寫成空值。
- `Collection expecting embedding with dimension ...`：目前 `KS_ROOT` 的 vector DB 不是用現在的 embedding model 建的。換新的 `KS_ROOT` 後重新 ingest。
- agent 只看到 `./ks`：它沒有 source `shared-runtime.sh`，或沒有跑 `discover-runtime.sh`。
