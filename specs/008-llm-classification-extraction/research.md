# Research: LLM-assisted classification and extraction

## Decision 1: 008 uses explicit preview/store modes, not automatic apply

**Decision**: `ks llm classify` defaults to preview/read-only. Explicit store mode may persist an extraction artifact under `KS_ROOT/llm/extractions/`, but no mode in 008 applies changes to wiki, graph, or vector.

**Rationale**: 008 is the foundation for 009/010/011. Auto-applying LLM output here would collapse boundaries between candidate extraction, wiki synthesis, graph mutation, and continuous update. It would also weaken write-back safety and make model mistakes authoritative.

**Alternatives considered**:

- Apply graph candidates immediately: rejected because 010 owns Graphify/graphification semantics and audit.
- Auto-write wiki summary: rejected because 009 owns LLM Wiki synthesis.
- Never store output: rejected because LLM extraction is expensive and later specs need auditable reuse.

## Decision 2: Provider abstraction is required, but no hosted provider is mandatory

**Decision**: Introduce a provider protocol and deterministic fake provider. Local/hosted providers may be added behind explicit config, but tests and baseline usage must run offline.

**Rationale**: HKS is local-first and agent-friendly. The project cannot require paid keys, network, or a specific LLM vendor for tests. A fake provider also makes contract tests stable.

**Alternatives considered**:

- Directly call one hosted provider: rejected because it violates local-first and makes CI nondeterministic.
- Hard-code a local model dependency: rejected because model installation is environment-specific and not required to define the contract.
- Let each agent handle LLM outside HKS: rejected because HKS would lose schema validation, provenance, artifact reuse, and adapter consistency.

## Decision 3: Output is normalized into HKS graph schema candidate types

**Decision**: Entity candidates are limited to `Person`, `Project`, `Document`, `Event`, `Concept`; relation candidates are limited to `owns`, `depends_on`, `impacts`, `references`, `belongs_to`.

**Rationale**: Current HKS graph schema is intentionally small and stable. Letting each provider invent labels would break graph queries and downstream Graphify input.

**Alternatives considered**:

- Permit arbitrary entity/relation strings: rejected because later graph ingestion would need lossy cleanup.
- Add new schema types in 008: rejected because there is no proven runtime need yet; type expansion is a separate contract change.

## Decision 4: Artifact idempotency key includes source and model lineage

**Decision**: Stored artifacts are keyed by source relpath, source fingerprint, parser fingerprint, prompt version, provider id, and model id.

**Rationale**: LLM output depends on both source content and extraction context. Reusing output across parser or prompt changes would corrupt provenance.

**Alternatives considered**:

- Key only by source relpath: rejected because content changes would reuse stale extractions.
- Key only by source hash: rejected because parser and prompt changes alter the extraction surface even when bytes are identical.

## Decision 5: Adapter support is part of the implementation scope

**Decision**: Implementation MUST expose `hks_llm_classify` through MCP and `/llm/classify` through loopback HTTP. CLI, MCP, and HTTP are co-equal agent surfaces in 008.

**Rationale**: 006 made MCP / HTTP formal agent surfaces. 008 is specifically useful to agents, so contract parity matters and FR-016 mandates MUST.

**Alternatives considered**:

- CLI only: rejected because agent clients would need shell wrapping and would lose adapter-level contract tests.
- HTTP only: rejected because HKS remains CLI-first.

## Decision 6: Hosted provider opt-in is gated by environment variables only

**Decision**: Hosted/network providers require all of: `HKS_LLM_NETWORK_OPT_IN=1`, `HKS_LLM_PROVIDER_<ID>_API_KEY` for the chosen provider (`<ID>` upper-cased `provider_id`), and optionally `HKS_LLM_PROVIDER_<ID>_ENDPOINT`. CLI flags, MCP request fields, and HTTP request bodies MUST NOT expose an opt-in toggle.

**Rationale**: Network egress is a high-impact safety setting. Allowing per-call opt-in via flags would let an agent silently flip it during a long-running session. Env-var-only gates align with existing HKS conventions (`HKS_*`) and force explicit operator intent at process launch. Combined with the deterministic fake provider for tests, this keeps CI offline by construction.

**Alternatives considered**:

- CLI flag (`--allow-network`): rejected because agent shells could enable it transparently mid-session.
- Config file under `KS_ROOT`: rejected because `KS_ROOT` is data-only; safety toggles do not belong in user data.
- Per-provider TOML config: deferred — env vars cover MVP needs and can be supplemented later without breaking the contract.
