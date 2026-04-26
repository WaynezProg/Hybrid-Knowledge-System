---
name: hks-knowledge-system
description: Operate the local Hybrid Knowledge System (HKS) repo and CLI safely. Use when Codex needs to ingest messy folders such as testhsk, query HKS knowledge, explain or run chunking and embedding behavior, add optional LLM classification/wiki synthesis, build Graphify artifacts, validate HKS runtime layers, or guide another agent through `ks ingest`, `ks query`, `ks llm classify`, `ks wiki synthesize`, `ks graphify build`, `ks lint`, and related `$KS_ROOT` workflows.
---

# HKS Knowledge System

## Overview

Use HKS as a local-first knowledge system. Treat `ks ingest` as the default indexing path, and treat LLM classification/wiki synthesis as explicit follow-up work, not automatic ingest behavior.

## Ground Rules

- Work in `/Users/waynetu/claw_prog/projects/09-HKS` unless the user points to another checkout.
- Use `uv run ...`; do not install Python/Node runtimes. If environment setup is needed, use `uv sync`.
- Keep `KS_ROOT` explicit for experiments so user data and repo fixtures do not mix.
- Before claiming behavior, check `README.md`, `docs/main.md`, and runtime code if the answer depends on current implementation.

## Decision Flow

If the user asks whether HKS “整理” messy files, answer precisely:

- `ks ingest <path>` copies originals to `$KS_ROOT/raw_sources`, parses/normalizes text, creates wiki pages, graph artifacts, vector chunks, embeddings, and `manifest.json`.
- `ks ingest` does not rename, move, rewrite, or semantically reorganize the original source folder.
- LLM-based整理 requires extra commands: `ks llm classify --mode store` then `ks wiki synthesize --mode store|apply`.

## Basic Ingest And Query

Use this for a messy folder when the user wants searchable knowledge but has not requested LLM-written synthesis:

```bash
cd /Users/waynetu/claw_prog/projects/09-HKS
uv sync
export KS_ROOT=/tmp/hks-testhsk-ks
uv run ks ingest /path/to/testhsk
uv run ks query "這批資料的重點是什麼？" --writeback=no
uv run ks lint --strict
```

Use `--writeback=no` for exploratory queries. Query auto write-back can create extra wiki pages when confidence is high.

## Chunk And Embedding

Chunking and embedding are default ingest behavior:

- Text is normalized, then split into chunks. Rich parsers may use segment-aware chunks for sheets, slides, table rows, OCR text, and headings.
- Embeddings are created for vector retrieval through `HKS_EMBEDDING_MODEL`; default is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- For deterministic offline tests, set `HKS_EMBEDDING_MODEL=simple`. This is good for smoke tests, not a quality benchmark.

Do not describe chunking/embedding as LLM work. It is tokenizer/model embedding infrastructure used by ingest and query retrieval.

## Optional LLM整理

Use this only when the user wants higher-level classification, extracted facts/entities/relations, or generated wiki pages.

```bash
uv run ks llm classify <source-relpath-from-manifest> --mode store --provider fake
uv run ks wiki synthesize --source-relpath <source-relpath-from-manifest> --target-slug <slug> --mode store --provider fake
uv run ks wiki synthesize --candidate-artifact-id <candidate-id> --mode apply --provider fake
```

Important boundaries:

- `ks llm classify --mode preview|store` does not mutate `wiki/`, `graph/`, or `vector/`; store writes `$KS_ROOT/llm/extractions/`.
- `ks wiki synthesize --mode preview|store` does not mutate authoritative wiki; store writes `$KS_ROOT/llm/wiki-candidates/`.
- `ks wiki synthesize --mode apply` is the explicit mutation step that writes `origin=llm_wiki` wiki pages.
- The default `fake` provider is deterministic and offline; hosted/network providers require explicit repo-supported configuration.

## Graphify And Visual整理

Use Graphify after ingest and optional LLM artifacts when the user wants communities, a static HTML graph, audit output, or derived relationship exploration.

```bash
uv run ks graphify build --mode preview --provider fake
uv run ks graphify build --mode store --provider fake
```

Graphify writes derived artifacts under `$KS_ROOT/graphify/`; it must not be presented as modifying authoritative `graph/graph.json`.

## Validation

After changing data or workflows, run focused checks:

```bash
uv run ks lint --strict
uv run pytest --tb=short -q
uv run ruff check .
uv run mypy src/hks
```

For user-facing claims, prefer a real smoke test with a temporary `KS_ROOT` and a small sample folder. Report what was actually run and whether LLM steps were included.
