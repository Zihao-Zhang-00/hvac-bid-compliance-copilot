"""Tests for uncertainty and human-review handling."""

import json

import pytest
from pydantic import ValidationError

from app.requirement_extractor import extract_requirements
from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
    TenderRequirement,
)
from app.requirement_uncertainty import (
    flag_uncertain_requirements,
)


def make_requirement(**changes):
    data = {
        "requirement_text": "Valid HVAC license required.",
        "category": "qualification",
        "mandatory": True,
        "source_page": 1,
        "evidence_needed": "Valid contractor license",
        "needs_review": False,
    }
    data.update(changes)
    return TenderRequirement.model_validate(data)


def review_one(**changes):
    original = make_requirement(**changes)
    result = RequirementExtractionResult(
        requirements=[original]
    )
    reviewed = flag_uncertain_requirements(result)
    return original, reviewed.requirements[0]


@pytest.mark.parametrize(
    "clause",
    [
        (
            "Additional compliance information should be supplied "
            "when considered appropriate by the evaluation committee."
        ),
        (
            "Additional records shall be submitted "
            "when deemed necessary by the committee."
        ),
        (
            "Extra documentation may be requested "
            "at the committee's discretion."
        ),
        (
            "Technical evidence must be supplied "
            "if requested by the evaluation committee."
        ),
    ],
)
def test_discretionary_requirements_need_review(clause):
    original, reviewed = review_one(
        requirement_text=clause,
        mandatory=False,
        source_page=5,
    )

    assert reviewed.mandatory is None
    assert reviewed.needs_review is True
    assert reviewed.requirement_text == clause
    assert reviewed.source_page == 5

    # The original model output is not mutated.
    assert original.mandatory is False


def test_unknown_category_requires_review():
    _, reviewed = review_one(
        category="unknown",
        mandatory=True,
    )

    assert reviewed.category == RequirementCategory.UNKNOWN
    assert reviewed.needs_review is True
    assert reviewed.mandatory is True


def test_unknown_mandatory_status_requires_review():
    _, reviewed = review_one(
        mandatory=None,
    )

    assert reviewed.mandatory is None
    assert reviewed.needs_review is True


def test_clear_optional_requirement_is_not_flagged():
    _, reviewed = review_one(
        requirement_text=(
            "Bidders may attach an optional installation "
            "schedule for reference."
        ),
        category="documentation",
        mandatory=False,
    )

    assert reviewed.mandatory is False
    assert reviewed.needs_review is False


def test_clear_mandatory_requirement_is_not_flagged():
    _, reviewed = review_one(
        requirement_text=(
            "All proposed units must use R-32 refrigerant."
        ),
        category="technical",
        mandatory=True,
    )

    assert reviewed.mandatory is True
    assert reviewed.needs_review is False


def test_existing_review_flag_is_preserved():
    _, reviewed = review_one(
        mandatory=False,
        needs_review=True,
    )

    assert reviewed.needs_review is True
    assert reviewed.mandatory is False


def test_missing_evidence_is_not_fabricated():
    _, reviewed = review_one(
        category="unknown",
        mandatory=None,
        evidence_needed=None,
    )

    assert reviewed.evidence_needed is None
    assert reviewed.needs_review is True


def test_empty_extraction_is_preserved():
    empty = RequirementExtractionResult(
        requirements=[]
    )

    reviewed = flag_uncertain_requirements(empty)

    assert reviewed.requirements == []


def test_extraction_pipeline_flags_ambiguous_clause():
    clause = (
        "Additional compliance information should be supplied "
        "when considered appropriate by the evaluation committee."
    )

    class FakeLLM:
        def complete(self, system_prompt, user_prompt):
            return json.dumps({
                "requirements": [{
                    "requirement_text": clause,
                    "category": "documentation",
                    "mandatory": False,
                    "source_page": 5,
                    "evidence_needed": None,
                    "needs_review": False,
                }]
            })

    result = extract_requirements(
        pages=[{"page_number": 5, "text": clause}],
        client=FakeLLM(),
    )

    requirement = result.requirements[0]

    assert requirement.source_page == 5
    assert requirement.requirement_text == clause
    assert requirement.mandatory is None
    assert requirement.needs_review is True


def test_missing_review_field_remains_invalid():
    data = make_requirement().model_dump(
        mode="json"
    )
    del data["needs_review"]

    class FakeLLM:
        def complete(self, system_prompt, user_prompt):
            return json.dumps({
                "requirements": [data]
            })

    with pytest.raises(ValidationError):
        extract_requirements(
            pages=[{
                "page_number": 1,
                "text": "Valid HVAC license required.",
            }],
            client=FakeLLM(),
        )
