from __future__ import annotations

import pytest

from hks.errors import KSError
from hks.llm.config import build_request
from hks.llm.models import SourceProvenance
from hks.llm.providers import provider_for
from hks.llm.validation import validate_provider_output


def _source() -> SourceProvenance:
    return SourceProvenance(
        source_relpath="project-atlas.txt",
        source_fingerprint="sha",
        parser_fingerprint="txt:v1",
    )


def test_validation_accepts_fake_provider_output() -> None:
    request = build_request(source_relpath="project-atlas.txt")
    result = validate_provider_output(
        provider_for(request).extract(request, content="Project Atlas"),
        request=request,
        source=_source(),
    )

    assert result.entity_candidates[0].type == "Document"
    assert result.relation_candidates[0].type == "references"


def test_validation_rejects_unsupported_entity_type() -> None:
    request = build_request(source_relpath="project-atlas.txt")
    payload = provider_for(request).extract(request, content="Project Atlas")
    payload["entity_candidates"][0]["type"] = "Company"

    with pytest.raises(KSError) as exc_info:
        validate_provider_output(payload, request=request, source=_source())

    assert exc_info.value.exit_code == 65


def test_validation_ignores_side_effect_text_with_finding() -> None:
    request = build_request(source_relpath="project-atlas.txt", provider="fake-side-effect")
    result = validate_provider_output(
        provider_for(request).extract(request, content="Project Atlas"),
        request=request,
        source=_source(),
    )

    assert result.findings[0].code == "side_effect_text_ignored"
