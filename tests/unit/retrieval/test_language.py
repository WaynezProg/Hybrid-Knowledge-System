from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from hks.errors import KSError
from hks.retrieval.language import language_scope, normalize, normalize_query


def test_normalizes_only_bounded_synonyms_and_keeps_query_name_case():
    assert normalize("等候 熱鍵 兼容性 隱憂 狀況") == "等待 快捷鍵 相容性 風險 狀態"
    assert normalize_query("IT US 等候") == "IT US 等待"
    assert normalize("阿特拉斯") == "阿特拉斯"
    assert normalize_query("目的地") == "目的地"


def test_aliases_are_workspace_local_bidirectional_and_boundary_aware(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "query_aliases.json").write_text(
        json.dumps({"session2memory": ["s2m", "會話記憶"], "IT": []})
    )
    with language_scope(first):
        assert normalize("S2M session2memory 會話記憶") == "session2memory " * 2 + "session2memory"
        assert normalize("s2m2 session2memory2") == "s2m2 session2memory2"
        assert normalize_query("İT") == "İT"
        with language_scope(second):
            assert normalize("s2m") == "s2m"
        assert normalize("s2m") == "session2memory"
    assert normalize("s2m") == "s2m"


@pytest.mark.parametrize(
    "payload",
    [[], {"A": "b"}, {"A": [""]}, {"A": ["b"], "B": []}, {"ERR-4012": ["ERR-4013"]}],
)
def test_invalid_or_ambiguous_alias_config_is_explicit_error(tmp_path, payload):
    (tmp_path / "query_aliases.json").write_text(json.dumps(payload))
    with pytest.raises(KSError, match="query_aliases.json"):
        with language_scope(tmp_path):
            pass


def test_concurrent_workspace_aliases_do_not_leak(tmp_path):
    roots = [tmp_path / str(n) for n in range(2)]
    for n, root in enumerate(roots):
        root.mkdir()
        (root / "query_aliases.json").write_text(
            json.dumps({f"Project{chr(65 + n)}": ["共享名稱"]})
        )

    def read(n):
        with language_scope(roots[n]):
            return normalize("共享名稱")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(read, [0, 1] * 5)) == ["projecta", "projectb"] * 5
