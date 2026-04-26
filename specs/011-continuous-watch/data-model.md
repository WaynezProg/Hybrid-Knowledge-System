# Data Model: Continuous update / watch workflow

## WatchRequest

Fields:

- `operation`: `scan | run | status`
- `mode`: `dry-run | execute`; default `dry-run`
- `profile`: `scan-only | ingest-only | derived-refresh | wiki-apply | full`; default `scan-only`
- `source_roots`: optional list of explicit filesystem roots
- `prune`: boolean; default `false`
- `include_llm`: boolean; default `false`
- `include_wiki_apply`: boolean; default `false`
- `include_graphify`: boolean; default `false`
- `force`: boolean; default `false`
- `requested_by`: optional agent/user string

Validation:

- `scan` is always read-only regardless of profile.
- External source changes can only be detected when `source_roots` are supplied or a saved watch config exists.
- When no source root is supplied, scan may inspect `$KS_ROOT/raw_sources` for internal consistency but MUST disclose that external source roots were not checked.
- `run` with `mode=dry-run` writes at most a watch plan artifact.
- `run` with `mode=execute` may call existing mutation services only when the selected profile permits that action.
- Hosted/network provider gates from 008/009/010 still apply.

## WatchRoot

Fields:

- `root_path`
- `kind`: `external | raw_sources`
- `created_at`
- `last_seen_at`

Rules:

- Relative source paths are computed from each `root_path` and compared against manifest relpaths.
- Saved watch config may reuse roots from the previous explicit scan/run.
- A missing external root is a plan issue, not a silent zero-change result.

## WatchSource

Fields:

- `relpath`
- `format`
- `state`: `unchanged | stale | new | missing | unsupported | corrupt`
- `current_sha256`
- `manifest_sha256`
- `current_parser_fingerprint`
- `manifest_parser_fingerprint`
- `size_bytes`
- `lineage_refs`
- `issues`

Rules:

- `stale` means content hash or parser fingerprint differs from manifest state.
- `new` means a supported source exists on disk but is absent from manifest.
- `missing` means manifest references a source absent from disk.
- `unsupported` and `corrupt` do not block scanning other sources.

## RefreshPlan

Fields:

- `plan_id`
- `schema_version`
- `created_at`
- `plan_fingerprint`
- `mode`
- `profile`
- `source_counts`
- `artifact_counts`
- `actions`
- `issues`

Fingerprint:

`plan_fingerprint = sha256(schema_version, mode, profile, sorted source observations, sorted lineage observations, action list)`

Rules:

- Same inputs MUST produce the same `plan_fingerprint`.
- Plan actions MUST be ordered deterministically by dependency and source relpath.
- Plans are derived artifacts and do not authorize mutation unless used by an explicit execute run.

## RefreshAction

Fields:

- `action_id`
- `kind`: `ingest | prune | llm_classify | wiki_synthesize | wiki_apply | graphify_build | report_issue`
- `source_relpath`
- `depends_on`
- `status`: `planned | skipped | running | completed | failed`
- `input_fingerprint`
- `output_refs`
- `error`

Rules:

- `wiki_apply` cannot be planned unless caller selects a profile that explicitly permits authoritative wiki mutation.
- `graphify_build` writes only `$KS_ROOT/graphify/` and must run after prerequisite ingest/lineage actions.
- Completed actions must be idempotent on retry.

## WatchRun

Fields:

- `run_id`
- `schema_version`
- `created_at`
- `completed_at`
- `status`: `planned | running | completed | failed | partial`
- `plan_id`
- `plan_fingerprint`
- `mode`
- `profile`
- `requested_by`
- `actions`
- `summary`

Rules:

- Store creates run state atomically and updates latest pointer only after validation.
- A partial run is detected when run metadata exists but required action/result artifacts are missing.
- Failed runs must preserve enough action state for a later retry.

## WatchSummaryDetail

Fields:

- `kind`: `watch_summary`
- `operation`
- `mode`
- `profile`
- `plan_id`
- `run_id`
- `plan_fingerprint`
- `source_counts`
- `action_counts`
- `artifacts`
- `idempotent_reuse`
- `confidence`

Rules:

- Top-level `source` remains limited to `wiki | graph | vector`.
- `watch_summary` is a trace step detail, not a new route/source enum.
- `scan`, `dry-run`, and `status` responses use `trace.route="wiki"` and `source=[]`.
- `execute` responses that run ingest use `trace.route="wiki"` and `source=["wiki","graph","vector"]`.
- Derived watch artifacts and graphify outputs are represented inside `watch_summary.artifacts`, not as top-level source values.

## Watch Latest Pointer

`$KS_ROOT/watch/latest.json` contains:

- `schema_version`
- `latest_plan_id`
- `latest_run_id`
- `updated_at`
- `plan_fingerprint`

Atomicity:

Store writes to temp files, validates JSON artifacts, then replaces latest pointer.
