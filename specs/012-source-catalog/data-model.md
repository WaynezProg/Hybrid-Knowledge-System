# Data Model: Source catalog and workspace selection

## SourceCatalogRequest

Fields:

- `ks_root`: optional explicit runtime root; otherwise resolved by existing `KS_ROOT` rules
- `format`: optional source format filter
- `relpath_query`: optional substring or prefix filter
- `limit`: optional positive integer
- `offset`: optional non-negative integer
- `include_integrity`: boolean; default `true`

Rules:

- Reads only existing runtime state.
- Missing or corrupt manifest maps to existing exit semantics.
- Empty filtered results are successful responses.

## SourceCatalogEntry

Fields:

- `relpath`
- `format`: `txt | md | pdf | docx | xlsx | pptx | png | jpg | jpeg`
- `size_bytes`
- `ingested_at`
- `sha256`
- `sha256_prefix`
- `parser_fingerprint`
- `derived_counts`
- `integrity_status`: `ok | warning | error | unknown`
- `issues`
- `query_hint`

Derived counts:

- `wiki_pages`
- `graph_nodes`
- `graph_edges`
- `vector_ids`

Rules:

- Entries sort by `relpath`.
- `query_hint` is advisory text, not a generated query.
- Integrity checks must not mutate runtime.

## SourceDetail

Fields:

- all `SourceCatalogEntry` fields
- `raw_source_path`
- `derived`
- `integrity_checks`

Derived:

- `wiki_pages`: list of wiki page slugs/paths from manifest
- `graph_nodes`: list of graph node ids from manifest
- `graph_edges`: list of graph edge ids from manifest
- `vector_ids`: list of vector ids from manifest

Rules:

- `raw_source_path` must be under `$KS_ROOT/raw_sources`.
- Source detail must not expose arbitrary file content.

## WorkspaceRegistry

Fields:

- `schema_version`
- `updated_at`
- `workspaces`: map of workspace id to `WorkspaceRecord`

Rules:

- Registry writes are atomic.
- A corrupt registry must not be overwritten automatically.
- Registry path resolution order: explicit CLI/adapter option → `$HKS_WORKSPACE_REGISTRY` → `$XDG_CONFIG_HOME/hks/workspaces.json` → `~/.config/hks/workspaces.json`. Tests must use explicit temporary registry paths.
- Registry must not persist any "last-used" / "current" workspace pointer; `workspace use` is stateless (see spec.md FR-011).
- `workspace register` against an existing id with a different resolved root MUST fail with conflict (exit `66`); `--force` overrides and the success response carries `previous_root` in `CatalogSummaryDetail`.

## WorkspaceRecord

Fields:

- `id`
- `label`
- `ks_root`
- `created_at`
- `updated_at`
- `tags`
- `metadata`

Validation:

- `id` must match `^[A-Za-z][A-Za-z0-9_-]{0,63}$` (ASCII letter start, alphanumeric / `-` / `_`, max 64 chars). See spec.md FR-009.
- `ks_root` is stored as a resolved absolute path.
- `metadata` must be a JSON object with scalar values only in MVP.

## WorkspaceStatus

Fields:

- `id`
- `label`
- `ks_root`
- `status`: `ready | missing | uninitialized | corrupt | duplicate_root`
- `source_count`
- `formats`
- `last_ingested_at`
- `issues`

Rules:

- Status is derived at read time from the registered root.
- `ready` requires readable `manifest.json`.
- Missing raw/derived artifacts can downgrade to warning status but must not mutate runtime.

## CatalogSummaryDetail

Required fields:

- `kind`: const `"catalog_summary"`
- `command`: `source.list | source.show | workspace.list | workspace.show | workspace.register | workspace.remove | workspace.use`
- `total_count`: integer ≥ 0
- `filtered_count`: integer ≥ 0
- `filter`: object of applied predicates, or `null` when no filter
- `warnings`: array of strings

Optional fields (presence depends on `command`):

- `workspace_id`: required for `workspace.show | workspace.register | workspace.remove | workspace.use`; optional for source-scoped commands when invoked via a workspace
- `ks_root`: resolved root for the operation
- `registry_path`: resolved registry file path for `workspace.*` commands
- `previous_root`: previous resolved root returned by `workspace.register --force` overwrite (null otherwise)
- `sources`: list payload for `source.list`
- `source`: single payload for `source.show`
- `workspaces`: status list for `workspace.list`
- `export_command`: shell-safe export string for `workspace.use`

Rules:

- Lives under `trace.steps[kind="catalog_summary"].detail`.
- Top-level `source` array remains the HKS stable enum and must not include `"catalog"` or `"workspace"`.
- Workspace query does not use `catalog_summary`; it returns the delegated query response.
- See spec.md FR-014 for the required field contract.
