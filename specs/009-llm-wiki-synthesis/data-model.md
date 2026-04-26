# Data Model: LLM-assisted wiki synthesis

## WikiSynthesisRequest

Represents a request to synthesize a wiki page from an 008 extraction artifact.

Fields:

- `source_relpath`: optional source relpath used by `preview` / `store` to find a matching 008 artifact.
- `extraction_artifact_id`: optional explicit 008 artifact id used by `preview` / `store`.
- `candidate_artifact_id`: optional stored 009 candidate artifact id required by `apply`.
- `mode`: `preview`, `store`, or `apply`.
- `target_slug`: optional requested wiki slug.
- `prompt_version`: synthesis prompt contract version.
- `provider_id`: synthesizer provider id, default fake/offline.
- `model_id`: synthesizer model id.
- `force_new_run`: boolean for candidate artifact storage.
- `requested_by`: optional agent/user label.

Validation:

- `mode=preview|store` requires one of `source_relpath` or `extraction_artifact_id` to resolve to a valid 008 artifact.
- `mode=apply` requires `candidate_artifact_id` to resolve to a schema-valid stored candidate artifact; missing stored candidate returns `66`.
- `mode=apply` must not regenerate a candidate or create a new candidate artifact.
- `mode=apply` must fail on lineage conflicts.
- Network/hosted providers inherit 008 env-gated opt-in behavior through `HKS_LLM_NETWORK_OPT_IN` and `HKS_LLM_PROVIDER_<ID>_API_KEY`; 009 does not add `HKS_WIKI_NETWORK_*` equivalents.

## WikiSynthesisCandidate

Represents a schema-validated wiki page candidate.

Fields:

- `candidate_id`: deterministic id derived from extraction artifact and synthesis lineage.
- `target_slug`: proposed wiki page slug.
- `title`: wiki page title.
- `summary`: frontmatter summary.
- `body`: markdown body.
- `source_relpath`: source relpath from upstream extraction artifact.
- `extraction_artifact_id`: upstream 008 artifact id.
- `source_fingerprint`: upstream raw source hash.
- `parser_fingerprint`: upstream parser fingerprint.
- `prompt_version`: synthesis prompt version.
- `provider_id`: synthesizer provider.
- `model_id`: synthesizer model.
- `confidence`: synthesis confidence.
- `diff_summary`: planned create/update/conflict information.
- `findings`: warnings such as side-effect text ignored; side-effect findings reuse 008 code `side_effect_text_ignored`.

Validation:

- `title`, `summary`, and `body` must be non-empty.
- `target_slug` must be stable, path-safe, and not contain traversal.
- If caller does not provide `target_slug`, synthesizer output title is normalized with `python-slugify` to produce the slug.
- `confidence` must be in `[0.0, 1.0]`.
- `wiki_synthesis_summary.confidence` must equal `candidate.confidence` for the single candidate returned by a 009 request.
- Candidate must not contain instructions to mutate graph, vector, manifest, raw sources, or external systems.

## WikiSynthesisArtifact

Represents a stored candidate under `KS_ROOT/llm/wiki-candidates/`.

Fields:

- `artifact_id`: deterministic id unless force new run is requested.
- `schema_version`: candidate artifact schema version.
- `idempotency_key`: extraction artifact + synthesis prompt + provider + target slug lineage.
- `created_at`: artifact creation timestamp.
- `status`: `valid`, `invalid`, or `partial`.
- `request`: normalized `WikiSynthesisRequest`.
- `candidate`: `WikiSynthesisCandidate`.

Lifecycle:

1. `preview`: artifact -> candidate -> response only.
2. `store`: artifact -> candidate -> atomic candidate artifact write -> response reference.
3. `apply`: stored candidate artifact -> stale check -> conflict check -> atomic wiki write -> index/log update -> response.

## WikiApplyResult

Represents the result of applying a candidate to the wiki layer.

Fields:

- `operation`: `create`, `update`, `conflict`, or `already_applied`.
- `touched_pages`: list of `pages/<slug>.md`.
- `target_slug`: applied or attempted slug.
- `log_entry_id`: timestamp or generated id for `wiki/log.md`.
- `conflicts`: list of conflict details.
- `diff_summary`: applied change summary.
- `idempotent_apply`: true when a concurrent or repeated apply finds the same lineage already applied.

Validation:

- `operation=conflict` must not write wiki files.
- `operation=create|update` must include at least one touched page and a log entry.
- `operation=already_applied` must set `idempotent_apply=true` and must not rewrite page content.

## Lineage Equality

Lineage is equal only when all of these fields match:

- `extraction_artifact_id`
- `source_fingerprint`
- `parser_fingerprint`

Rules:

- Differences in `prompt_version`, `provider_id`, or `model_id` are update metadata, not lineage conflicts.
- Existing target pages with `origin` other than `llm_wiki` are always conflicts.
- Same-lineage repeated apply returns an idempotent result instead of overwriting.

## WikiLineage

Represents provenance from applied wiki page back to raw source.

Fields:

- `wiki_slug`
- `wiki_origin`: `llm_wiki`
- `wiki_candidate_artifact_id`
- `extraction_artifact_id`
- `source_relpath`
- `source_fingerprint`
- `parser_fingerprint`
- `prompt_version`
- `provider_id`
- `model_id`

Validation:

- Applied page lineage must resolve to the stored candidate and upstream 008 extraction artifact at apply time.

## Applied Wiki Page Frontmatter

Represents the required frontmatter fields for pages written by 009 `apply`.

Fields:

- `title`: candidate title.
- `summary`: candidate summary.
- `origin`: `llm_wiki`.
- `slug`: applied wiki slug.
- `generated_at`: apply timestamp.
- `source_relpath`: upstream source relpath.
- `source_fingerprint`: upstream source fingerprint at apply time.
- `extraction_artifact_id`: upstream 008 artifact id.
- `wiki_candidate_artifact_id`: stored 009 candidate artifact id.
- `prompt_version`: synthesis prompt version.
- `provider_id`: synthesizer provider id.
- `model_id`: synthesizer model id.

Validation:

- `origin=llm_wiki` pages must not be parsed as `origin=ingest` or `origin=writeback`.
- Missing lineage fields are lint findings, not silent defaults.
- Existing wiki frontmatter for `ingest` and `writeback` pages remains valid after adding `llm_wiki`.
- Valid `origin=llm_wiki` pages are exempt from existing wiki-to-manifest reconciliation because they derive from stored synthesis candidates, not raw source manifest entries.

## Apply Atomicity

Apply writes must follow this sequence:

1. Acquire the same fcntl-based lock pattern used by 008 candidate storage.
2. Validate the stored candidate artifact and target page lineage after lock acquisition.
3. Write `pages/<slug>.md.tmp`.
4. Rename temp page to `pages/<slug>.md`.
5. Rebuild `wiki/index.md`.
6. Append `wiki/log.md`.

If any step after temp write fails before log append, implementation must roll back the page write or leave a lint-detectable partial apply finding.
