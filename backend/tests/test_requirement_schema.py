
import json

import pytest
from pydantic import ValidationError

from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
    TenderRequirement,
)


@pytest.fixture
def valid_data():
    return {
        "requirement_text": "The equipment COP must be at least 5.8.",
        "category": "technical",
        "mandatory": True,
        "source_page": 12,
        "evidence_needed": "Manufacturer technical datasheet",
        "needs_review": False,
    }


def test_valid_requirement(valid_data):
    requirement = TenderRequirement.model_validate(valid_data)

    assert requirement.category == RequirementCategory.TECHNICAL
    assert requirement.source_page == 12


def test_result_serializes_to_json(valid_data):
    requirement = TenderRequirement.model_validate(valid_data)
    result = RequirementExtractionResult(requirements=[requirement])

    encoded = result.model_dump_json()
    parsed = json.loads(encoded)

    assert parsed["requirements"][0]["category"] == "technical"
    assert RequirementExtractionResult.model_validate_json(encoded) == result


def test_unknown_information_is_supported(valid_data):
    valid_data.update(
        category="unknown",
        mandatory=None,
        evidence_needed=None,
        needs_review=True,
    )

    requirement = TenderRequirement.model_validate(valid_data)

    assert requirement.mandatory is None
    assert requirement.category == RequirementCategory.UNKNOWN
    assert requirement.needs_review is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_page", 0),
        ("source_page", "12"),
        ("category", "environmental"),
        ("requirement_text", "   "),
        ("mandatory", "yes"),
    ],
)
def test_invalid_values_rejected(valid_data, field, value):
    valid_data[field] = value

    with pytest.raises(ValidationError):
        TenderRequirement.model_validate(valid_data)


def test_missing_required_field_rejected(valid_data):
    del valid_data["mandatory"]

    with pytest.raises(ValidationError):
        TenderRequirement.model_validate(valid_data)


def test_unexpected_field_rejected(valid_data):
    valid_data["fake_confidence"] = 0.99

    with pytest.raises(ValidationError):
        TenderRequirement.model_validate(valid_data)
