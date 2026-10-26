"""Conservative uncertainty handling for tender requirements."""

import re

from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
)


# A small, auditable set of phrases indicating conditional
# obligations dependent on evaluation committee discretion.
_DISCRETIONARY_PATTERNS = (
    re.compile(
        r"\bwhen (?:considered|deemed) "
        r"(?:appropriate|necessary)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:at|subject to) (?:the )?"
        r"(?:evaluation )?committee(?:['’]s)? discretion\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bif (?:requested|required) by (?:the )?"
        r"(?:evaluation )?committee\b",
        re.IGNORECASE,
    ),
)


def flag_uncertain_requirements(
    result: RequirementExtractionResult,
) -> RequirementExtractionResult:
    """Flag ambiguous obligations without fabricating information."""

    reviewed = []

    for requirement in result.requirements:
        discretionary = any(
            pattern.search(requirement.requirement_text)
            for pattern in _DISCRETIONARY_PATTERNS
        )

        needs_review = (
            requirement.needs_review
            or requirement.mandatory is None
            or requirement.category == RequirementCategory.UNKNOWN
            or discretionary
        )

        mandatory = (
            None if discretionary else requirement.mandatory
        )

        reviewed.append(
            requirement.model_copy(
                update={
                    "mandatory": mandatory,
                    "needs_review": needs_review,
                }
            )
        )

    return RequirementExtractionResult(
        requirements=reviewed
    )
