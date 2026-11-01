"""Unit and integration tests for conservative quote-review flags."""

import json
import logging

from app.requirement_extractor import extract_requirements
from app.requirement_quote_review import flag_unmatched_source_quotes
from app.requirement_schema import RequirementExtractionResult, TenderRequirement


SOURCE = (
    "All proposals must include the following attachments:\n"
    "1. Proof of current EPA 608 certification for all technicians\n"
    "2. Copies of relevant business licenses\n"
    "3. Certificate of Insurance (meeting requirements in Section 6.5)"
)
COMBINED = (
    "All proposals must include the following attachments: "
    "2. Copies of relevant business licenses"
)


def make_requirement(**changes):
    item = {
        "requirement_text": "2. Copies of relevant business licenses",
        "category": "documentation",
        "mandatory": True,
        "source_page": 9,
        "evidence_needed": "Business license copy",
        "needs_review": False,
    }
    item.update(changes)
    return TenderRequirement.model_validate(item)


def review_one(requirement, source=SOURCE):
    result = RequirementExtractionResult(requirements=[requirement])
    return flag_unmatched_source_quotes(
        result, [{"page_number": 9, "text": source}]
    ).requirements[0]


def test_exact_bullet_stays_unflagged():
    assert review_one(make_requirement()).needs_review is False


def test_whitespace_normalized_quote_matches():
    item = make_requirement(
        requirement_text="2.   Copies of relevant   business licenses"
    )
    assert review_one(item).needs_review is False


def test_concatenated_heading_and_bullet_flagged(caplog):
    with caplog.at_level(logging.WARNING):
        item = review_one(make_requirement(requirement_text=COMBINED))
    assert item.needs_review is True
    assert "Non-verbatim requirement" in caplog.text


def test_other_fields_preserved_and_input_not_mutated():
    original = make_requirement(requirement_text=COMBINED)
    updated = review_one(original)
    assert updated.requirement_text == original.requirement_text
    assert updated.source_page == original.source_page
    assert updated.category == original.category
    assert updated.mandatory == original.mandatory
    assert updated.evidence_needed == original.evidence_needed
    assert original.needs_review is False
    assert updated.needs_review is True


def test_existing_review_flag_preserved():
    assert review_one(make_requirement(needs_review=True)).needs_review is True


def test_text_missing_entirely_is_flagged():
    item = review_one(make_requirement(requirement_text="Unrelated clause"))
    assert item.needs_review is True


def test_empty_result_preserved():
    result = flag_unmatched_source_quotes(
        RequirementExtractionResult(requirements=[]),
        [{"page_number": 9, "text": SOURCE}],
    )
    assert result.requirements == []


def test_multiple_records_handled_independently():
    first = make_requirement()
    second = make_requirement(requirement_text=COMBINED)
    result = flag_unmatched_source_quotes(
        RequirementExtractionResult(requirements=[first, second]),
        [{"page_number": 9, "text": SOURCE}],
    )
    assert [item.needs_review for item in result.requirements] == [False, True]


def test_pipeline_flags_nonverbatim_quote():
    record = make_requirement(requirement_text=COMBINED)

    class ReplayLLM:
        def complete(self, system_prompt, user_prompt):
            return json.dumps({"requirements": [record.model_dump(mode="json")]})

    result = extract_requirements(
        [{"page_number": 9, "text": SOURCE}], ReplayLLM()
    )
    assert result.requirements[0].needs_review is True
    assert result.requirements[0].requirement_text == COMBINED
    assert result.requirements[0].source_page == 9
