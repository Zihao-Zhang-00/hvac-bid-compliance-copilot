"""Tests for requirement validation and normalization."""

import json

import pytest
from pydantic import ValidationError

from app.requirement_validation import (
    validate_and_normalize_requirements,
)


def make_requirement(**changes):
    requirement = {
        "requirement_text": "Valid HVAC license required.",
        "category": "qualification",
        "mandatory": True,
        "source_page": 1,
        "evidence_needed": "Valid license",
        "needs_review": False,
    }
    requirement.update(changes)
    return requirement


def validate(records, pages=None):
    if pages is None:
        pages = {1}

    return validate_and_normalize_requirements(
        json.dumps({"requirements": records}),
        pages,
    )


def test_valid_requirement_serializes():
    result = validate([make_requirement()])

    assert len(result.requirements) == 1
    assert json.loads(result.model_dump_json())[
        "requirements"
    ][0]["category"] == "qualification"


def test_blank_evidence_becomes_none():
    result = validate([
        make_requirement(evidence_needed="   ")
    ])

    assert result.requirements[0].evidence_needed is None


def test_requirement_text_is_trimmed():
    result = validate([
        make_requirement(
            requirement_text="  Valid HVAC license required.  "
        )
    ])

    assert (
        result.requirements[0].requirement_text
        == "Valid HVAC license required."
    )


def test_exact_duplicate_is_removed():
    item = make_requirement()

    result = validate([item, item.copy()])

    assert len(result.requirements) == 1


def test_conflicting_duplicate_is_rejected():
    first = make_requirement(category="qualification")
    second = make_requirement(category="documentation")

    with pytest.raises(ValueError, match="Conflicting duplicate"):
        validate([first, second])


@pytest.mark.parametrize(
    "changes",
    [
        {"category": "invalid-category"},
        {"mandatory": "yes"},
        {"source_page": "1"},
        {"needs_review": "false"},
        {"requirement_text": "   "},
    ],
)
def test_invalid_fields_are_rejected(changes):
    with pytest.raises(ValidationError):
        validate([make_requirement(**changes)])


def test_missing_review_flag_is_rejected():
    item = make_requirement()
    del item["needs_review"]

    with pytest.raises(ValidationError):
        validate([item])


def test_nonexistent_source_page_is_rejected():
    with pytest.raises(ValueError, match="source page"):
        validate([make_requirement(source_page=99)])


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        validate([
            make_requirement(fake_confidence=0.95)
        ])


def test_malformed_json_is_rejected():
    with pytest.raises(ValidationError):
        validate_and_normalize_requirements(
            "{not-json}",
            {1},
        )


def test_empty_response_is_rejected():
    with pytest.raises(ValueError, match="non-empty"):
        validate_and_normalize_requirements("", {1})


def test_empty_requirements_are_allowed():
    result = validate([])

    assert result.requirements == []
