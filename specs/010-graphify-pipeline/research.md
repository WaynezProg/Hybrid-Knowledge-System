# Research: Graphify pipeline

## Decisions

### R1. Derived artifacts, not authoritative graph mutation

Decision: Store Graphify outputs under `$KS_ROOT/graphify/` and never write them into `graph/graph.json`.

Rationale: HKS ingestion graph is deterministic source-derived state. Graphify adds inferred/ambiguous analysis edges and community clusters; mixing those into `graph/graph.json` would change query semantics and break lint expectations.

Rejected alternative: Update `graph/graph.json` directly. Rejected because inferred edges would become indistinguishable from extracted ingestion edges unless graph schema becomes more complex.

### R2. Deterministic local clustering by default

Decision: Use deterministic local graph connectivity / label-propagation style clustering for v1, with stable sorting and no new mandatory dependency.

Rationale: Tests must be deterministic and local-first. Existing dependencies are enough for a personal-scale graph.

Rejected alternative: Add `networkx` or external graph DB. Rejected for 010 because it increases dependency surface before runtime need is proven.

### R3. LLM is optional classification, not graph authority

Decision: Optional LLM provider may label communities or summarize audit rationale, but default classification is deterministic and hosted provider remains env-gated.

Rationale: User asked for LLM-assisted classification, but Constitution requires local-first and no network dependency.

Rejected alternative: Make hosted LLM required for Graphify. Rejected because it would break offline testability and existing provider gate discipline.

### R4. Static HTML is artifact, not UI

Decision: Store `graph.html` as static local output generated from run JSON.

Rationale: Visualization is part of Graphify deliverables, but a server/web app would violate current non-goals.

Rejected alternative: Serve interactive UI from `hks-api`. Rejected because 010 is not a UI spec.

### R5. Contract surface mirrors 008/009 adapter pattern

Decision: CLI `ks graphify build`, MCP `hks_graphify_build`, HTTP `/graphify/build`, all returning direct HKS top-level success payloads.

Rationale: 006/008/009 already established adapter parity; 010 should not create shell-only behavior.

Rejected alternative: CLI-only Graphify. Rejected due agent contract drift.

### R6. Static visualization uses inline SVG and degrades for large graphs

Decision: Generate static HTML with inline SVG and small inline JavaScript only for local interaction; no framework, remote script, CDN, or server dependency. For graphs over 500 nodes, default to a community-first list/table view with optional SVG summary rather than rendering every edge.

Rationale: 010 needs inspectable local visualization without becoming a UI project or bloating artifacts.

Rejected alternative: Bundle D3 or a frontend framework. Rejected because dependency and bundle size are unnecessary for v1 and would blur the current no-UI boundary.
