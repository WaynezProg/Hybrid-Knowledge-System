from __future__ import annotations

from hks.adapters import core


def test_mcp_core_catalog_tools(tmp_path, working_docs) -> None:
    registry = tmp_path / "workspaces.json"
    ks_root = tmp_path / "ks"
    core.hks_ingest(path=str(working_docs), ks_root=str(ks_root))

    sources = core.hks_source_list(ks_root=str(ks_root))
    assert sources["trace"]["steps"][0]["detail"]["command"] == "source.list"

    detail = core.hks_source_show(relpath="project-atlas.txt", ks_root=str(ks_root))
    assert detail["trace"]["steps"][0]["detail"]["source"]["relpath"] == "project-atlas.txt"

    registered = core.hks_workspace_register(
        workspace_id="proj-a",
        ks_root=str(ks_root),
        registry_path=str(registry),
    )
    assert registered["trace"]["steps"][0]["detail"]["workspace_id"] == "proj-a"

    query = core.hks_workspace_query(
        workspace_id="proj-a",
        question="Atlas",
        writeback="no",
        registry_path=str(registry),
    )
    assert query["source"]

