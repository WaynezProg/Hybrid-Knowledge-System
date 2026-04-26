# Research: LLM-assisted wiki synthesis

## Decision 1: 009 consumes 008 artifacts; it does not redo extraction

**Decision**: 009 requires a valid 008 extraction artifact or a source relpath with a matching stored artifact. If no artifact exists, the command returns `66` and instructs the caller to run `ks llm classify <source-relpath> --mode store`.

**Rationale**: 008 owns classification/extraction. Re-running extraction implicitly inside 009 would make provenance ambiguous and hide LLM cost/side effects from the caller.

**Alternatives considered**:

- Auto-run 008 extraction when missing: rejected because it hides a second LLM operation and weakens auditability.
- Accept raw source directly and synthesize wiki: rejected because it bypasses 008 schema validation and evidence normalization.

## Decision 2: Preview/store/apply are separate modes

**Decision**: 009 supports `preview`, `store`, and explicit `apply`. Preview and store are read-only with respect to authoritative wiki; apply is the only mode that changes `wiki/pages/`, `wiki/index.md`, and `wiki/log.md`. Apply requires a stored `candidate_artifact_id` and never regenerates or creates a candidate artifact.

**Rationale**: LLM Wiki output can pollute the knowledge base if applied silently. Separating modes keeps review, staging, and commit semantics clear for agents and humans.

**Alternatives considered**:

- Apply by default: rejected because it violates write-back safety.
- Preview only: rejected because 009 must actually provide a path to persistent LLM Wiki pages.
- Store only: rejected because users would still need a second unstandardized apply mechanism.
- Apply by re-running synthesis: rejected because it makes the approved candidate non-auditable and can diverge from the reviewed artifact.

## Decision 3: Applied pages use `origin=llm_wiki`

**Decision**: 009 introduces a distinguishable wiki page origin value `llm_wiki` for applied synthesis pages.

**Rationale**: Existing origins `ingest` and `writeback` do not capture synthesis-from-artifact semantics. A separate origin allows lint, audit, and future 011 workflows to reason about lineage.

**Alternatives considered**:

- Reuse `writeback`: rejected because writeback pages are query-answer artifacts, not source-synthesis pages.
- Reuse `ingest`: rejected because applied LLM Wiki pages are not raw-source parser outputs.

## Decision 4: 009 does not update graph or vector

**Decision**: Apply mode modifies only the wiki layer. Graphify remains 010; cross-layer continuous refresh remains 011.

**Rationale**: Applying synthesized text to vector or graph would create a second source of truth before graphification and refresh policy exist. It also risks embedding model drift and duplicate retrieval content.

**Alternatives considered**:

- Re-embed applied wiki pages immediately: rejected because vector ownership and dedupe policy belong in 011.
- Convert candidate entities to graph on apply: rejected because 010 owns Graphify semantics and audit.

## Decision 5: Candidate artifacts are stored separately

**Decision**: Store mode writes versioned candidates under `KS_ROOT/llm/wiki-candidates/`; candidate artifact `request.mode` is always `store`.

**Rationale**: 008 extraction artifacts are upstream data; 009 candidate artifacts are synthesized wiki pages. Keeping them separate avoids mixing raw extraction candidates with edited page drafts.

**Alternatives considered**:

- Store candidates inside `wiki/pages/` as drafts: rejected because draft pages would affect index/lint/query semantics.
- Store candidates inside 008 extraction artifact: rejected because it mutates upstream artifact lineage.

## Decision 6: Adapter parity is required

**Decision**: CLI, MCP, and loopback HTTP must expose the same wiki synthesis capability.

**Rationale**: 006 made MCP/HTTP formal agent surfaces. 009 is agent-facing and must not force non-shell agents to wrap CLI manually.

**Alternatives considered**:

- CLI only: rejected because it creates adapter drift.
- HTTP only: rejected because HKS remains CLI-first.
