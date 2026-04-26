from __future__ import annotations

from hks.llm import prompts


def test_prompt_template_has_no_domain_specific_taxonomy() -> None:
    template = prompts.EXTRACTION_PROMPT_TEMPLATE.lower()

    for forbidden in ("legal", "medical", "source code", "company policy"):
        assert forbidden not in template
