from __future__ import annotations

from pathlib import Path

import pytest

from hks.cli import app
from hks.core.paths import runtime_paths
from hks.storage.wiki import WikiStore


@pytest.mark.integration
def test_wiki_reconcile_finds_no_orphans_or_dead_links(
    cli_runner,
    working_docs: Path,
    tmp_ks_root: Path,
) -> None:
    ingest_result = cli_runner.invoke(app, ["ingest", str(working_docs)])
    assert ingest_result.exit_code == 0

    for question in ("summary Atlas", "Project A summary", "clause 3.2 text"):
        result = cli_runner.invoke(app, ["query", question, "--writeback=yes"])
        assert result.exit_code == 0

    wiki_store = WikiStore(runtime_paths(tmp_ks_root))
    assert wiki_store.reconcile() == {"orphans": [], "dead_links": []}
