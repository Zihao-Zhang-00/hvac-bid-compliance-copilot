"""Validate and normalize LLM-extracted tender requirements."""

from app.requirement_schema import RequirementExtractionResult


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
            if seen[key] != requirement:
                raise ValueError(
                    "Conflicting duplicate requirement: "
                    f"page {requirement.source_page}"
                )
            continue

        seen[key] = requirement
        unique_requirements.append(requirement)

    return RequirementExtractionResult(
        requirements=unique_requirements
    )
