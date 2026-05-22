from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from hks.core.paths import runtime_paths
from hks.storage.wiki import WikiStore


@pytest.mark.unit
def test_wiki_mutation_lock_serializes_threads_sharing_one_store(tmp_path: Path) -> None:
    store = WikiStore(runtime_paths(tmp_path / "ks"))
    acquired: list[str] = []

    def mutate() -> None:
        with store.locked_mutation():
            acquired.append("worker")

    with store.locked_mutation():
        thread = threading.Thread(target=mutate)
        thread.start()
        time.sleep(0.1)
        assert acquired == []

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert acquired == ["worker"]
