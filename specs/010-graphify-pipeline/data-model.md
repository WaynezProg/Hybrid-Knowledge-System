# Data Model: Graphify pipeline

## GraphifyRequest

Fields:

- `mode`: `preview | store`; default `preview`
- `provider_id`: classification provider id; default `fake`
- `model_id`: classification model id; default deterministic fake graphify classifier
- `algorithm_version`: deterministic clustering/build version
- `include_html`: boolean; default `true` for store
- `include_report`: boolean; default `true` for store
- `force_new_run`: boolean; default `false`
- `requested_by`: optional agent/user string

Validation:

- `preview` is read-only and cannot write `$KS_ROOT/graphify/`.
- `store` writes only `$KS_ROOT/graphify/`.
- Hosted providers require `HKS_LLM_NETWORK_OPT_IN=1` and `HKS_LLM_PROVIDER_<ID>_API_KEY`.

## GraphifyRun

Fields:

- `run_id`
- `schema_version`
- `created_at`
- `status`: `valid | invalid | partial`
- `idempotency_key`
- `input_fingerprint`
- `algorithm_version`
- `request`
- `artifacts`

Artifacts:

- `graphify.json`
- `communities.json`
- `audit.json`
- `manifest.json`
- `graph.html` when enabled
- `GRAPH_REPORT.md` when enabled

Idempotency:

`idempotency_key = sha256(schema_version, input_fingerprint, algorithm_version, provider_id, model_id, include_html, include_report)`

When `force_new_run=true`, the key MUST include a `created_at_iso` salt:

`idempotency_key = sha256(schema_version, input_fingerprint, algorithm_version, provider_id, model_id, include_html, include_report, created_at_iso)`

## GraphifyGraph

Top-level fields:

- `schema_version`
- `nodes`
- `edges`
- `communities`
- `audit_findings`
- `input_layers`
- `generated_at`

## GraphifyNode

Fields:

- `id`
- `label`
- `kind`: `source | wiki_page | entity | concept | artifact | community`
- `source_layer`: `wiki | graph | llm_extraction | llm_wiki | graphify`
- `source_ref`
- `provenance`
- `community_id`

Rules:

- `source_layer="graphify"` is allowed inside graphify artifacts only, not in HKS top-level `source`.
- IDs must be deterministic and stable for the same input fingerprint.

## GraphifyEdge

Fields:

- `id`
- `source`
- `target`
- `relation`
- `evidence`: `EXTRACTED | INFERRED | AMBIGUOUS`
- `confidence_score`: number `0.0..1.0`
- `weight`
- `source_layer`
- `source_ref`
- `rationale`

Rules:

- `EXTRACTED` means direct HKS graph edge, wiki link, manifest relationship, or explicit artifact lineage.
- `INFERRED` means deterministic Graphify inference such as co-membership or shared provenance.
- `AMBIGUOUS` means low-confidence or conflicting evidence that should be reviewed.

## GraphifyCommunity

Fields:

- `community_id`
- `label`
- `summary`
- `node_ids`
- `representative_edge_ids`
- `classification_method`: `deterministic | llm`
- `confidence_score`
- `provenance`

## GraphifyAuditFinding

Fields:

- `severity`: `info | warning | error`
- `code`
- `message`
- `source_ref`
- `evidence`

Initial codes:

- `graphify_no_analyzable_input`: default severity `info`
- `graphify_invalid_graph`: default severity `warning`
- `graphify_invalid_wiki_page`: default severity `warning`
- `graphify_corrupt_upstream_artifact`: default severity `warning`
- `graphify_partial_run`: default severity `error`
- `graphify_latest_mismatch`: default severity `error`
- `side_effect_text_ignored`: default severity `warning`

Partial-run lint definition:

- Lint MUST NOT trust a run artifact self-reporting `status="partial"` as the only signal.
- A partial run is detected when a run directory exists but any required artifact is missing: `graphify.json`, `communities.json`, `audit.json`, or `manifest.json`.
- `status="partial"` is only an auxiliary note that store may leave before an interrupted finalize.

## Latest Pointer

`$KS_ROOT/graphify/latest.json` contains:

- `schema_version`
- `run_id`
- `run_manifest_path`
- `updated_at`
- `input_fingerprint`

Atomicity:

Store writes into a temporary run directory first, validates all JSON artifacts, then renames to the final run directory and updates `latest.json`.
