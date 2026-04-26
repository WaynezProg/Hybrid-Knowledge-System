"""Validation and normalization for LLM extraction output."""

from __future__ import annotations

from typing import Any, cast

from hks.adapters.contracts import validate_llm_summary
from hks.core.manifest import utc_now_iso
from hks.errors import ExitCode, KSError
from hks.llm.models import (
    ENTITY_TYPES,
    RELATION_TYPES,
    ClassificationLabel,
    EntityCandidate,
    EntityType,
    Evidence,
    KeyFact,
    LlmExtractionRequest,
    LlmExtractionResult,
    LlmFinding,
    ProviderMetadata,
    RelationCandidate,
    RelationType,
    SourceProvenance,
)


def validate_provider_output(
    payload: dict[str, Any],
    *,
    request: LlmExtractionRequest,
    source: SourceProvenance,
) -> LlmExtractionResult:
    findings: list[LlmFinding] = []
    if "side_effect_text" in payload:
        findings.append(
            LlmFinding(
                severity="warning",
                code="side_effect_text_ignored",
                message="provider side-effect text was ignored",
            )
        )
    try:
        result = LlmExtractionResult(
            operation="llm_classify",
            mode=request.mode,
            source=source,
            provider=ProviderMetadata(
                provider_id=request.provider.provider_id,
                model_id=request.provider.model_id,
                prompt_version=request.prompt_version,
                generated_at=utc_now_iso(),
            ),
            classification=_classification(payload.get("classification"), source.source_relpath),
            summary_candidate=_optional_text(payload.get("summary_candidate")),
            key_facts=_key_facts(payload.get("key_facts"), source.source_relpath),
            entity_candidates=_entities(payload.get("entity_candidates"), source.source_relpath),
            relation_candidates=_relations(
                payload.get("relation_candidates"),
                source.source_relpath,
            ),
            confidence=_confidence(payload.get("confidence")),
            findings=findings,
        )
        _validate_relation_references(result)
        validate_llm_summary(result.to_detail())
        return result
    except KSError:
        raise
    except Exception as exc:
        raise KSError(
            "LLM provider output validation failed",
            exit_code=ExitCode.DATAERR,
            code="LLM_OUTPUT_INVALID",
            details=[str(exc)],
        ) from exc


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("summary_candidate must be a non-empty string or null")
    return value.strip()


def _confidence(value: Any) -> float:
    if not isinstance(value, int | float):
        raise ValueError("confidence must be numeric")
    number = float(value)
    if number < 0.0 or number > 1.0:
        raise ValueError("confidence must be in [0.0, 1.0]")
    return number


def _evidence_items(value: Any, source_relpath: str) -> list[Evidence]:
    if not isinstance(value, list):
        raise ValueError("evidence must be an array")
    items: list[Evidence] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("evidence item must be an object")
        evidence_source = str(item.get("source_relpath") or "")
        if evidence_source != source_relpath:
            raise ValueError("evidence source_relpath does not match requested source")
        quote = str(item.get("quote") or "")
        if not quote:
            raise ValueError("evidence quote is required")
        start = item.get("start_offset")
        end = item.get("end_offset")
        if start is not None and (not isinstance(start, int) or start < 0):
            raise ValueError("evidence start_offset must be a non-negative integer or null")
        if end is not None and (not isinstance(end, int) or end < 0):
            raise ValueError("evidence end_offset must be a non-negative integer or null")
        if isinstance(start, int) and isinstance(end, int) and end < start:
            raise ValueError("evidence end_offset must be >= start_offset")
        items.append(
            Evidence(
                source_relpath=evidence_source,
                chunk_id=cast(str | None, item.get("chunk_id")),
                quote=quote,
                start_offset=start,
                end_offset=end,
            )
        )
    return items


def _classification(value: Any, source_relpath: str) -> list[ClassificationLabel]:
    if not isinstance(value, list):
        raise ValueError("classification must be an array")
    labels: list[ClassificationLabel] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("classification item must be an object")
        label = str(item.get("label") or "").strip()
        if not label:
            raise ValueError("classification label is required")
        labels.append(
            ClassificationLabel(
                label=label,
                confidence=_confidence(item.get("confidence")),
                evidence=_evidence_items(item.get("evidence"), source_relpath),
            )
        )
    return labels


def _key_facts(value: Any, source_relpath: str) -> list[KeyFact]:
    if not isinstance(value, list):
        raise ValueError("key_facts must be an array")
    facts: list[KeyFact] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("key_facts item must be an object")
        fact = str(item.get("fact") or "").strip()
        if not fact:
            raise ValueError("key fact text is required")
        facts.append(
            KeyFact(
                fact=fact,
                confidence=_confidence(item.get("confidence")),
                evidence=_evidence_items(item.get("evidence"), source_relpath),
            )
        )
    return facts


def _entities(value: Any, source_relpath: str) -> list[EntityCandidate]:
    if not isinstance(value, list):
        raise ValueError("entity_candidates must be an array")
    entities: list[EntityCandidate] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("entity candidate must be an object")
        entity_type = str(item.get("type") or "")
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity type: {entity_type}")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
            raise ValueError("aliases must be an array of strings")
        entities.append(
            EntityCandidate(
                candidate_id=_required_text(item, "candidate_id"),
                type=cast(EntityType, entity_type),
                label=_required_text(item, "label"),
                aliases=list(aliases),
                confidence=_confidence(item.get("confidence")),
                evidence=_evidence_items(item.get("evidence"), source_relpath),
            )
        )
    return entities


def _relations(value: Any, source_relpath: str) -> list[RelationCandidate]:
    if not isinstance(value, list):
        raise ValueError("relation_candidates must be an array")
    relations: list[RelationCandidate] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("relation candidate must be an object")
        relation_type = str(item.get("type") or "")
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"unsupported relation type: {relation_type}")
        source_id = _required_text(item, "source_candidate_id")
        target_id = _required_text(item, "target_candidate_id")
        if source_id == target_id:
            raise ValueError("self-relation candidates are not supported")
        relations.append(
            RelationCandidate(
                candidate_id=_required_text(item, "candidate_id"),
                type=cast(RelationType, relation_type),
                source_candidate_id=source_id,
                target_candidate_id=target_id,
                confidence=_confidence(item.get("confidence")),
                evidence=_evidence_items(item.get("evidence"), source_relpath),
            )
        )
    return relations


def _required_text(item: dict[str, Any], field: str) -> str:
    value = str(item.get(field) or "").strip()
    if not value:
        raise ValueError(f"{field} is required")
    return value


def _validate_relation_references(result: LlmExtractionResult) -> None:
    entity_ids = {entity.candidate_id for entity in result.entity_candidates}
    for relation in result.relation_candidates:
        if relation.source_candidate_id not in entity_ids:
            raise ValueError(f"relation source does not exist: {relation.source_candidate_id}")
        if relation.target_candidate_id not in entity_ids:
            raise ValueError(f"relation target does not exist: {relation.target_candidate_id}")
