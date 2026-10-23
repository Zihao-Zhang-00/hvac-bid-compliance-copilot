import json
from pathlib import Path

import pytest

from app.requirement_schema import (
    RequirementCategory,
    RequirementExtractionResult,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tender_data():
    path = FIXTURES_DIR / "sample_tender_pages.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def expected_data():
    path = FIXTURES_DIR / "expected_requirements.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_tender_pages_have_valid_numbers_and_text(tender_data):
    pages = tender_data["pages"]
    assert len(pages) == 6
    assert [page["page_number"] for page in pages] == [1, 2, 3, 4, 5, 6]
    assert all(isinstance(page["text"], str) and page["text"].strip() for page in pages)


def test_expected_requirements_follow_schema(expected_data):
    result = RequirementExtractionResult.model_validate(expected_data)
    assert len(result.requirements) == 10
    assert json.loads(result.model_dump_json()) == expected_data


def test_each_requirement_matches_its_source_page(tender_data, expected_data):
    page_text = {page["page_number"]: page["text"] for page in tender_data["pages"]}
    result = RequirementExtractionResult.model_validate(expected_data)

    for requirement in result.requirements:
        assert requirement.source_page in page_text
        assert requirement.requirement_text in page_text[requirement.source_page]


def test_five_supported_categories_are_represented(expected_data):
    result = RequirementExtractionResult.model_validate(expected_data)
    categories = {r.category for r in result.requirements}
    assert {
        RequirementCategory.QUALIFICATION,
        RequirementCategory.PERSONNEL,
        RequirementCategory.SCORING,
        RequirementCategory.TECHNICAL,
        RequirementCategory.DOCUMENTATION,
    }.issubset(categories)


def test_optional_and_uncertain_requirements_exist(expected_data):
    result = RequirementExtractionResult.model_validate(expected_data)
    assert any(r.mandatory is False for r in result.requirements)
    assert any(
        r.mandatory is None
        and r.category == RequirementCategory.UNKNOWN
        and r.needs_review is True
        for r in result.requirements
    )


def test_background_information_is_not_a_requirement(expected_data):
    result = RequirementExtractionResult.model_validate(expected_data)
    assert all(r.source_page != 6 for r in result.requirements)
