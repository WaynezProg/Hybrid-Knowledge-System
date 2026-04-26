# HKS Skill Framework

這個資料夾是給 Claude、OpenClaw、Codex 或其他 agent 讀的 CLI-first 操作框架。它不取代 repo README；它把 agent 執行 HKS 時最容易踩錯的入口、邊界、流程拆開。

## Layout

```text
skill/hks-knowledge-system/
├── SKILL.md
├── README.md
├── agents/
│   ├── claude.md
│   └── openclaw.md
├── config/
│   ├── discover-runtime.sh
│   └── shared-runtime.sh
├── commands/
│   └── cli.md
├── contracts/
│   └── response-contract.md
├── policies/
│   └── safety.md
├── troubleshooting.md
└── workflows/
    ├── ingest-query.md
    ├── llm-wiki-graphify.md
    ├── multi-agent.md
    ├── persistent-workspace.md
    ├── smoke-test.md
    └── watch-refresh.md
```

## Responsibility

- `SKILL.md`：最小入口，告訴 agent 何時用、先讀什麼、不可違反什麼。
- `commands/cli.md`：完整 `ks` CLI command map。
- `config/discover-runtime.sh`：列出目前 workspace 內的 ignored local runtime candidates，避免 agent 只看 tracked repo 或 `./ks`。
- `config/shared-runtime.sh`：讓多個 local agents 共用同一個 repo-local `KS_ROOT` 與 workspace registry。
- `workflows/`：可直接執行的任務流程。
- `contracts/`：response shape 與 semantic rules。
- `policies/`：環境、mutation、adapter 分界。
- `agents/`：不同 agent 的短入口。
- `troubleshooting.md`：常見誤判與修正。

## Adapter Boundary

這個 skill 資料夾只處理主要 CLI。MCP / HTTP adapter 的 config、tool manifest、HTTP request examples 放在 repo root 的 `mcp/`。
