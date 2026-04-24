from __future__ import annotations

import pytest

from hks.ingest.extractor import extract
from hks.ingest.models import ParsedDocument


@pytest.mark.unit
@pytest.mark.us1
def test_extract_builds_wiki_page_and_chunks() -> None:
    parsed = ParsedDocument(
        title="Project Atlas",
        body="Atlas body",
        format="md",
    )

    extracted = extract(
        relpath="notes/project-atlas.md",
        sha256="abc123",
        parsed=parsed,
        normalized_text="Atlas keeps pricing, auth, and events aligned.",
        chunks=["Atlas keeps pricing", "auth and events aligned"],
    )

    assert extracted.title == "Project Atlas"
    assert extracted.summary == "Atlas keeps pricing, auth, and events aligned."
    assert extracted.body.startswith("# Project Atlas\n\n")
    assert extracted.chunks == ["Atlas keeps pricing", "auth and events aligned"]
