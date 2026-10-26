"""Regression and conflict tests for conservative requirement classification."""

import json
from pathlib import Path

import pytest

from app.requirement_classifier import classify_requirements
from app.requirement_extractor import extract_requirements
from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
    TenderRequirement,
)

FIXTURES = Path(__file__).parent / "fixtures"


def make_requirement(text, category="documentation", **changes):
    values = {
        "requirement_text": text,
        "category": category,
        "mandatory": True,
        "source_page": 2,
        "evidence_needed": None,
        "needs_review": False,
    }
    values.update(changes)
    return TenderRequirement.model_validate(values)


def classify_one(text, category="documentation", **changes):
    original = make_requirement(text, category, **changes)
    classified = classify_requirements(
        RequirementExtractionResult(requirements=[original])
    )
    assert len(classified.requirements) == 1
    return original, classified.requirements[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Bidders must provide references for two completed HVAC projects.",
            RequirementCategory.QUALIFICATION,
        ),
        (
            "The contractor must have a valid HVAC license.",
            RequirementCategory.QUALIFICATION,
        ),
        (
            "The proposed project manager must hold a professional engineering license.",
            RequirementCategory.PERSONNEL,
        ),
        (
            "Resumes of installation technicians may be included.",
            RequirementCategory.PERSONNEL,
        ),
        (
            "Up to 10 evaluation points will be awarded for better COP.",
            RequirementCategory.SCORING,
        ),
        (
            "All proposed units must use R-32 refrigerant.",
            RequirementCategory.TECHNICAL,
        ),
        (
            "The bid package must include a signed compliance declaration form.",
            RequirementCategory.DOCUMENTATION,
        ),
        (
            "Bidders may attach an optional installation schedule for reference.",
            RequirementCategory.DOCUMENTATION,
        ),
    ],
)
def test_supported_categories(text, expected):
    _, actual = classify_one(text)
    assert actual.category == expected
    assert actual.needs_review is False


def test_generic_discretionary_material_is_unknown():
    original, actual = classify_one(
        "Additional compliance information should be supplied "
        "when considered appropriate by the evaluation committee.",
        mandatory=None,
        source_page=5,
        needs_review=True,
    )
    assert actual.category == RequirementCategory.UNKNOWN
    assert actual.needs_review is True
    assert actual.mandatory is None
    assert actual.requirement_text == original.requirement_text
    assert actual.source_page == 5


def test_generic_committee_request_is_unknown():
    _, actual = classify_one(
        "Supplementary documents may be supplied if requested by the committee."
    )
    assert actual.category == RequirementCategory.UNKNOWN
    assert actual.needs_review is True


def test_conflicting_personnel_and_qualification_signals_require_review():
    _, actual = classify_one(
        "The bidder's project manager must hold a valid engineering license."
    )
    assert actual.category == RequirementCategory.UNKNOWN
    assert actual.needs_review is True


def test_unmatched_requirement_preserves_llm_category():
    _, actual = classify_one(
        "The supplier shall comply with all applicable safety standards.",
        category="technical",
    )
    assert actual.category == RequirementCategory.TECHNICAL
    assert actual.needs_review is False


def test_unknown_llm_category_is_not_silently_forced():
    _, actual = classify_one(
        "All proposed units must use R-32 refrigerant.",
        category="unknown",
    )
    assert actual.category == RequirementCategory.UNKNOWN
    assert actual.needs_review is True


def test_review_flag_and_noncategory_fields_are_preserved():
    original, actual = classify_one(
        "The project manager must hold an engineering license.",
        category="qualification",
        mandatory=False,
        source_page=9,
        evidence_needed="License certificate",
        needs_review=True,
    )
    assert actual.category == RequirementCategory.PERSONNEL
    assert actual.needs_review is True
    for field in ("mandatory", "source_page", "requirement_text", "evidence_needed"):
        assert getattr(actual, field) == getattr(original, field)
    assert original.category == RequirementCategory.QUALIFICATION


def test_empty_list_is_supported():
    result = classify_requirements(RequirementExtractionResult(requirements=[]))
    assert result.requirements == []


def test_mocked_pipeline_corrects_reference_and_manager():
    rows = [
        make_requirement(
            "Bidders must provide references for two completed HVAC projects.",
            category="documentation",
        ).model_dump(mode="json"),
        make_requirement(
            "The project manager must hold a professional engineering license.",
            category="qualification",
        ).model_dump(mode="json"),
    ]

    class FakeLLM:
        def complete(self, system_prompt, user_prompt):
            return json.dumps({"requirements": rows})

    pages = [{"page_number": 2, "text": " ".join(row["requirement_text"] for row in rows)}]
    result = extract_requirements(pages, FakeLLM())
    assert [r.category for r in result.requirements] == [
        RequirementCategory.QUALIFICATION,
        RequirementCategory.PERSONNEL,
    ]


def test_synthetic_fixture_categories_are_correct_after_classification():
    tender = json.loads(
        (FIXTURES / "sample_tender_pages.json").read_text(encoding="utf-8")
    )
    expected = RequirementExtractionResult.model_validate_json(
        (FIXTURES / "expected_requirements.json").read_text(encoding="utf-8")
    )
    # Deliberately inject the three category errors observed in the Qwen baseline.
    predicted = [r.model_copy() for r in expected.requirements]
    for index, wrong_category in ((1, "documentation"), (2, "qualification"), (9, "documentation")):
        predicted[index] = predicted[index].model_copy(
            update={"category": RequirementCategory(wrong_category)}
        )
    class FakeLLM:
        def complete(self, system_prompt, user_prompt):
            return json.dumps({
                "requirements": [r.model_dump(mode="json") for r in predicted]
            })

    result = extract_requirements(tender["pages"], FakeLLM())
    assert [r.category for r in result.requirements] == [
        r.category for r in expected.requirements
    ]
    assert [r.source_page for r in result.requirements] == [
        r.source_page for r in expected.requirements
    ]