"""Validate and normalize LLM-extracted tender requirements."""

import logging

from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
)

logger = logging.getLogger(__name__)


def validate_and_normalize_requirements(
    raw_json: str,
    valid_page_numbers: set[int],
) -> RequirementExtractionResult:
    """Reject invalid output and normalize safe, deterministic fields."""

    if not isinstance(raw_json, str) or not raw_json.strip():
        raise ValueError("LLM response must be non-empty JSON text")

    result = RequirementExtractionResult.model_validate_json(raw_json)

    unique_requirements = []
    seen = {}

    for requirement in result.requirements:
        if requirement.source_page not in valid_page_numbers:
            raise ValueError(
                "LLM returned a source page absent from input: "
                f"{requirement.source_page}"
            )

        # A blank evidence suggestion means evidence is unknown.
        if requirement.evidence_needed == "":
            requirement = requirement.model_copy(
                update={"evidence_needed": None}
            )

        key = (
            requirement.source_page,
            requirement.requirement_text,
        )

        if key in seen:
            index = seen[key]
            previous = unique_requirements[index]

            if previous != requirement:
                logger.warning(
                    "Conflicting duplicate on page %s: %r | "
                    "category=%s/%s mandatory=%s/%s evidence=%r/%r; "
                    "human review required",
                    requirement.source_page,
                    requirement.requirement_text,
                    previous.category.value,
                    requirement.category.value,
                    previous.mandatory,
                    requirement.mandatory,
                    previous.evidence_needed,
                    requirement.evidence_needed,
                )
                unique_requirements[index] = previous.model_copy(
                    update={
                        "category": (
                            previous.category
                            if previous.category == requirement.category
                            else RequirementCategory.UNKNOWN
                        ),
                        "mandatory": (
                            previous.mandatory
                            if previous.mandatory == requirement.mandatory
                            else None
                        ),
                        "evidence_needed": (
                            previous.evidence_needed
                            if previous.evidence_needed == requirement.evidence_needed
                            else None
                        ),
                        "needs_review": True,
                    }
                )
            continue

        seen[key] = len(unique_requirements)
        unique_requirements.append(requirement)

    return RequirementExtractionResult(
        requirements=unique_requirements
    )
