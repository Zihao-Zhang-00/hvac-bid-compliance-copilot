"""Quarantine unsupported LLM category names for human review.

This does not repair malformed or incomplete model output. Downstream
Pydantic validation still checks the complete response strictly.
"""

import json
import logging

from app.requirement_schema import RequirementCategory

logger = logging.getLogger(__name__)
SUPPORTED_CATEGORIES = frozenset(category.value for category in RequirementCategory)


def quarantine_unsupported_categories(raw_json: str) -> str:
    """Convert unsupported category strings to unknown + explicit review.

    Preserve every other field. Do not fabricate missing review flags or
    substitute values for wrong-type fields. Invalid JSON remains invalid.
    """
    if not isinstance(raw_json, str):
        return raw_json

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json

    if not isinstance(payload, dict):
        return raw_json

    records = payload.get("requirements")
    if not isinstance(records, list):
        return raw_json

    changed = False
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue

        category = record.get("category")
        if not isinstance(category, str) or category in SUPPORTED_CATEGORIES:
            continue

        # Missing / wrong-type review flags must still fail schema validation.
        if type(record.get("needs_review")) is not bool:
            continue

        logger.warning(
            "Quarantined unsupported LLM category at index %d: %r",
            index,
            category,
        )
        record["category"] = RequirementCategory.UNKNOWN.value
        record["needs_review"] = True
        changed = True

    return json.dumps(payload, ensure_ascii=False) if changed else raw_json
