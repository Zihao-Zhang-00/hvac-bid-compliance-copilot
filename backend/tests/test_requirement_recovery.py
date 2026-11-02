"""Regression tests for unsupported-category recovery discovered in Oxford RFP."""

import json
import logging

import pytest
from pydantic import ValidationError

from app.requirement_extractor import extract_requirements
from app.requirement_recovery import quarantine_unsupported_categories


OXFORD_CLAUSE = (
    "The contractor agrees to indemnify, defend, and hold harmless "
    "Oxford Preparatory School, its board members, officers, employees, "
    "and agents from any and all claims, damages, losses, and expenses "
    "arising out of or resulting from the contractor's performance "
    "under this agreement."
)


def make_record(**overrides):
    record = {
        "requirement_text": OXFORD_CLAUSE,
        "category": "liability",
        "mandatory": True,
        "source_page": 12,
        "evidence_needed": None,
        "needs_review": False,
    }
    record.update(overrides)
    return record


def as_json(record):
    return json.dumps({"requirements": [record]})


class FakeLLM:
    def __init__(self, raw):
        self.raw = raw

    def complete(self, system_prompt, user_prompt):
        return self.raw


def extract_one(record, *, pages=None):
    if pages is None:
        pages = [{"page_number": 12, "text": OXFORD_CLAUSE}]
    return extract_requirements(pages, FakeLLM(as_json(record)))


def test_oxford_liability_is_quarantined_and_logged(caplog):
    with caplog.at_level(logging.WARNING):
        actual = extract_one(make_record()).requirements[0]
    assert actual.category.value == "unknown"
    assert actual.needs_review is True
    assert actual.source_page == 12
    assert actual.requirement_text == OXFORD_CLAUSE
    assert actual.mandatory is True
    assert actual.evidence_needed is None
    assert "unsupported LLM category" in caplog.text


def test_original_json_is_not_mutated_and_other_fields_preserved():
    record = make_record(evidence_needed="Contract indemnity clause")
    raw = as_json(record)
    fixed = json.loads(quarantine_unsupported_categories(raw))["requirements"][0]
    assert json.loads(raw)["requirements"][0] == record
    assert {k: fixed[k] for k in record if k not in ("category", "needs_review")} == {
        k: record[k] for k in record if k not in ("category", "needs_review")
    }


def test_existing_review_flag_is_preserved():
    actual = extract_one(make_record(needs_review=True)).requirements[0]
    assert actual.needs_review is True


def test_valid_category_is_unchanged():
    raw = as_json(make_record(category="qualification"))
    assert quarantine_unsupported_categories(raw) == raw


def test_already_unknown_category_is_flagged_by_uncertainty_guard():
    actual = extract_one(make_record(category="unknown")).requirements[0]
    assert actual.category.value == "unknown"
    assert actual.needs_review is True


def test_empty_result_is_allowed():
    result = extract_requirements(
        [{"page_number": 1, "text": "Introduction only."}],
        FakeLLM('{"requirements": []}'),
    )
    assert result.requirements == []


def test_invalid_json_still_rejected():
    raw = '{"requirements": ['
    assert quarantine_unsupported_categories(raw) == raw
    with pytest.raises(ValidationError):
        extract_requirements(
            [{"page_number": 12, "text": OXFORD_CLAUSE}], FakeLLM(raw)
        )


def test_missing_review_flag_still_rejected():
    record = make_record()
    del record["needs_review"]
    with pytest.raises(ValidationError):
        extract_one(record)


@pytest.mark.parametrize("flag", ["false", None, 0])
def test_invalid_review_flag_still_rejected(flag):
    with pytest.raises(ValidationError):
        extract_one(make_record(needs_review=flag))


@pytest.mark.parametrize("invalid", [None, 123, ["liability"]])
def test_nonstring_category_still_rejected(invalid):
    with pytest.raises(ValidationError):
        extract_one(make_record(category=invalid))


def test_missing_category_still_rejected():
    record = make_record()
    del record["category"]
    with pytest.raises(ValidationError):
        extract_one(record)


def test_page_not_in_input_still_rejected():
    with pytest.raises(ValueError, match="source page"):
        extract_one(make_record(source_page=99, requirement_text="This clause is not in the input document."))


def test_wrong_page_type_still_rejected():
    with pytest.raises(ValidationError):
        extract_one(make_record(source_page="12"))


def test_extra_fields_still_rejected():
    with pytest.raises(ValidationError):
        extract_one(make_record(fake_confidence=0.99))


def test_wrong_top_level_shape_remains_invalid():
    raw = '[{"category": "liability"}]'
    assert quarantine_unsupported_categories(raw) == raw
    with pytest.raises(ValidationError):
        extract_requirements(
            [{"page_number": 12, "text": OXFORD_CLAUSE}], FakeLLM(raw)
        )


def test_wrong_requirements_shape_remains_invalid():
    raw = '{"requirements": {"category": "liability"}}'
    assert quarantine_unsupported_categories(raw) == raw
    with pytest.raises(ValidationError):
        extract_requirements(
            [{"page_number": 12, "text": OXFORD_CLAUSE}], FakeLLM(raw)
        )
