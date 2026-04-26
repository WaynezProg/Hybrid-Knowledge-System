# Data Model: LLM-assisted classification and extraction

## LlmProviderConfig

Represents the provider selected for one extraction run.

Fields:

- `provider_id`: stable provider name, e.g. `fake`, `local`, or a hosted provider id.
- `model_id`: model identifier as reported by the provider.
- `endpoint`: optional local or hosted endpoint.
- `network_opt_in`: boolean; hosted/network calls require `true`.
- `timeout_seconds`: provider call timeout.
- `credential_status`: `not_required`, `present`, or `missing`.

Validation:

- Hosted/network providers require `network_opt_in=true`.
- Tests must use `provider_id=fake`.
- Missing credentials fail before provider invocation.

## LlmExtractionRequest

Represents a request to classify/extract one already ingested source.

Fields:

- `source_relpath`: raw source relpath under `KS_ROOT/raw_sources/` or manifest source key.
- `mode`: `preview` or `store`.
- `prompt_version`: semantic prompt contract version. If caller omits, system MUST resolve to the current `src/hks/llm/prompts.py` `CURRENT_VERSION`. The resolved version (not the caller's null/empty input) MUST be persisted in any stored artifact and reflected in the response.
- `provider`: `LlmProviderConfig`.
- `force_new_run`: boolean; defaults to `false`.
- `requested_by`: optional agent/user label.

Validation:

- `source_relpath` must resolve inside existing HKS runtime state.
- Request cannot target arbitrary filesystem paths outside known runtime sources.
- `mode=preview` cannot write extraction artifacts.
- Hosted/network `provider` MUST satisfy the env-var opt-in gate (see spec FR-022 and research Decision 6) before request is dispatched; missing gate fails with exit `2 USAGE` before any provider call.

## LlmExtractionResult

Represents schema-validated LLM output before optional artifact storage.

Fields:

- `classification`: list of labels with confidence and evidence.
- `summary_candidate`: concise wiki-ready but not wiki-applied summary text.
- `key_facts`: fact statements with confidence and evidence.
- `entity_candidates`: list of `EntityCandidate`.
- `relation_candidates`: list of `RelationCandidate`.
- `confidence`: aggregate confidence in `[0.0, 1.0]`.
- `evidence`: source evidence spans or chunk references.
- `source_fingerprint`: raw source hash used for the run.
- `parser_fingerprint`: parser fingerprint from manifest.
- `prompt_version`: prompt contract version.
- `provider_id`: provider used for generation.
- `model_id`: model used for generation.
- `generated_at`: ISO-8601 timestamp.
- `schema_version`: artifact/detail schema version.
- `validation_status`: `valid` or `invalid`.

Validation:

- `confidence` and per-item confidence values must be bounded between `0.0` and `1.0`.
- Aggregate `confidence` MUST equal the minimum of all per-item confidences across `classification`, `key_facts`, `entity_candidates`, and `relation_candidates`. When the result has zero items in every category, `confidence` MUST be `0.0`. This conservative aggregation keeps caller decisions stable when one weak candidate is present.
- Evidence references must point to the requested source.
- Unsupported entity or relation types are rejected before response emission.

## EntityCandidate

Represents a candidate graph entity.

Fields:

- `candidate_id`: stable id inside one extraction result.
- `type`: one of `Person`, `Project`, `Document`, `Event`, `Concept`.
- `label`: canonical display label.
- `aliases`: optional alternate labels.
- `confidence`: candidate confidence.
- `evidence`: evidence references.

Relationships:

- Referenced by `RelationCandidate.source_candidate_id` and `RelationCandidate.target_candidate_id`.

## RelationCandidate

Represents a candidate graph relation.

Fields:

- `candidate_id`: stable id inside one extraction result.
- `type`: one of `owns`, `depends_on`, `impacts`, `references`, `belongs_to`.
- `source_candidate_id`: entity candidate id.
- `target_candidate_id`: entity candidate id.
- `confidence`: relation confidence.
- `evidence`: evidence references.

Validation:

- Source and target ids must exist in the same extraction result.
- Self-relations are rejected unless explicitly allowed by future graph contracts.

## ExtractionArtifact

Represents a stored extraction run under `KS_ROOT/llm/extractions/`.

Fields:

- `artifact_id`: deterministic id derived from idempotency key unless forced new run.
- `schema_version`: integer schema version.
- `idempotency_key`: source + parser + prompt + provider + model lineage.
- `request`: normalized `LlmExtractionRequest`.
- `result`: `LlmExtractionResult`.
- `created_at`: artifact write timestamp.
- `status`: `valid`, `invalid`, or `partial`.

On-disk layout:

- Artifacts are written flat under `KS_ROOT/llm/extractions/<artifact_id>.json` (no per-source subdirectories in 008). Quickstart commands like `find ... -maxdepth 1` rely on this layout.

Lifecycle:

1. `preview`: request -> provider -> validation -> response only.
2. `store`: request -> (atomic reuse of existing artifact under the same `idempotency_key` if present, otherwise provider call) -> validation -> atomic artifact write -> response with artifact reference. Concurrent writers for the same `idempotency_key` MUST converge on a single artifact (using HKS coordination lock from 007 / `fcntl`-style file lock); the late writer MUST reuse the existing artifact and the response MUST set `idempotent_reuse=true`. `force_new_run=true` bypasses reuse and writes a new `artifact_id`.
3. `apply`: out of scope for 008.
