# CLI Command Surface

正式 CLI entrypoint 是 `ks`，不是 `hsk`。

## Core

```bash
uv run ks --help
uv run ks ingest <file-or-dir>
uv run ks query "<question>" --writeback=no
uv run ks lint --strict
```

## Catalog And Workspace

```bash
uv run ks source list
uv run ks source show <source-relpath>
uv run ks workspace register <id> --ks-root <path> --label <label>
uv run ks workspace list
uv run ks workspace show <id>
uv run ks workspace use <id>
uv run ks workspace query <id> "<question>" --writeback=no
uv run ks workspace remove <id>
```

## Coordination

```bash
uv run ks coord session start <agent-id>
uv run ks coord session heartbeat <agent-id>
uv run ks coord session close <agent-id>
uv run ks coord lease claim <agent-id> <resource>
uv run ks coord lease renew <agent-id> <resource>
uv run ks coord lease release <agent-id> <resource>
uv run ks coord handoff add <agent-id> --summary "<summary>" --next-action "<next>"
uv run ks coord status
uv run ks coord lint
```

## LLM Extraction And Wiki Synthesis

```bash
uv run ks llm classify <source-relpath> --mode preview --provider fake
uv run ks llm classify <source-relpath> --mode store --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath> --target-slug <slug> --mode preview --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath> --target-slug <slug> --mode store --provider fake
uv run ks wiki synthesize --candidate-artifact-id <candidate-id> --mode apply --provider fake
```

## Graphify

```bash
uv run ks graphify build --mode preview --provider fake
uv run ks graphify build --mode store --provider fake
uv run ks graphify build --mode store --no-html --provider fake
```

## Watch

```bash
uv run ks watch scan --source-root <source-dir>
uv run ks watch run --source-root <source-dir> --mode dry-run --profile ingest-only
uv run ks watch run --source-root <source-dir> --mode execute --profile ingest-only
uv run ks watch status
```

## Supported Ingest Formats

```text
txt
md
pdf
docx
xlsx
pptx
png
jpg
jpeg
```
