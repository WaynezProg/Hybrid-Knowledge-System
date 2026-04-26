# Archive: 012 Source catalog and workspace selection

**Status**: Complete  
**Archived on**: 2026-04-26  
**Merged into**: pending merge to `main`

## Runtime Surface

- `ks source list`
- `ks source show <relpath>`
- `ks workspace register|list|show|remove|use|query`
- MCP tools `hks_source_list`, `hks_source_show`, `hks_workspace_list`, `hks_workspace_register`, `hks_workspace_show`, `hks_workspace_remove`, `hks_workspace_use`, `hks_workspace_query`
- HTTP endpoints `/catalog/sources`, `/catalog/sources/{relpath}`, `/workspaces`, `/workspaces/{workspace_id}`, `/workspaces/{workspace_id}/query`

## Contract Notes

- Source catalog and workspace management use `trace.steps[kind="catalog_summary"]`.
- Top-level `source` and `trace.route` enums are unchanged.
- `ks workspace query` delegates to existing `ks query` and returns normal query semantics.
- Workspace registry is a separate local JSON file, configurable through `HKS_WORKSPACE_REGISTRY`; it is not part of any single `$KS_ROOT`.

## Verification

Final verification is recorded in the implementation handoff after full repo gates complete.
