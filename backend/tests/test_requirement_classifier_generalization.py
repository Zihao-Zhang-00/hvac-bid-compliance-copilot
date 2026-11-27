"""Regression tests using additional HVAC tender phrasings."""

import pytest

from app.requirement_classifier import classify_requirements
from app.requirement_schema import (
    RequirementExtractionResult,
    TenderRequirement,
)


@pytest.mark.parametrize(
    ("clause", "initial", "expected", "review"),
    [
        (
            "Contractors shall submit references for three completed district cooling projects.",
            "documentation", "qualification", False,
        ),
        (
            "The site supervisor shall provide a current safety training certificate.",
            "qualification", "personnel", False,
        ),
        (
            "A weighted score will be assigned for each innovative energy solution.",
            "documentation", "scoring", False,
        ),
        (
            "The cooling capacity shall not fall below 450 kW.",
            "documentation", "technical", False,
        ),
        (
            "Please submit a completed compliance form with the bid.",
            "qualification", "documentation", False,
        ),
        (
            "Further documents should be provided if requested by the evaluation committee.",
            "documentation", "unknown", True,
        ),
        (
            "The contractor must submit a signed compliance declaration form and provide a valid registration.",
            "documentation", "unknown", True,
        ),
        (
            "Up to 12 evaluation points may be awarded for lower refrigerant leakage.",
            "technical", "scoring", False,
        ),
    ],
)
def test_additional_phrasings(clause, initial, expected, review):
    original = TenderRequirement(
        requirement_text=clause,
        category=initial,
        mandatory=True,
        source_page=1,
        evidence_needed=None,
        needs_review=False,
    )

    result = classify_requirements(
        RequirementExtractionResult(requirements=[original])
    )

    actual = result.requirements[0]

    assert actual.category.value == expected
    assert actual.needs_review is review
    assert actual.requirement_text == original.requirement_text
    assert actual.source_page == original.source_page
    assert actual.mandatory == original.mandatory
    assert actual.evidence_needed == original.evidence_needed
