"""Safe source-page recovery using provided-page exact evidence."""

import json
import logging

import pytest
from pydantic import ValidationError

from app.requirement_extractor import extract_requirements
from app.requirement_provenance import reconcile_source_pages


CLAUSE = "• Proposed contract length (1, 3, or 5 years)"


def record(**changes):
    item = dict(
        requirement_text=CLAUSE,
        category="documentation",
        mandatory=True,
        source_page=9,
        evidence_needed=None,
        needs_review=False,
    )
    item.update(changes)
    return item


def raw(item):
    return json.dumps({"requirements": [item]})


class ReplayLLM:
    def __init__(self, response):
        self.response = response

    def complete(self, system_prompt, user_prompt):
        return self.response


def extract(item, pages):
    return extract_requirements(pages, ReplayLLM(raw(item)))


def test_wrong_page_uniquely_matched_and_reviewed(caplog):
    with caplog.at_level(logging.WARNING):
        result = extract(record(), [{"page_number": 8, "text": CLAUSE}])
    item = result.requirements[0]
    assert item.source_page == 8
    assert item.needs_review is True
    assert item.requirement_text == CLAUSE
    assert "Corrected LLM source page" in caplog.text


def test_wrong_page_10_also_corrected():
    result = extract(record(source_page=10), [{"page_number": 8, "text": CLAUSE}])
    assert result.requirements[0].source_page == 8
    assert result.requirements[0].needs_review is True


def test_correct_page_is_not_modified():
    original = raw(record(source_page=8))
    assert reconcile_source_pages(original, [{"page_number": 8, "text": CLAUSE}]) == original
    result = extract(record(source_page=8), [{"page_number": 8, "text": CLAUSE}])
    assert result.requirements[0].needs_review is False


def test_ambiguous_quote_is_not_silently_repaired():
    pages = [{"page_number": 7, "text": CLAUSE}, {"page_number": 8, "text": CLAUSE}]
    with pytest.raises(ValueError, match="source page"):
        extract(record(source_page=10), pages)


def test_missing_quote_is_not_silently_repaired():
    with pytest.raises(ValueError, match="source page"):
        extract(record(), [{"page_number": 8, "text": "Entirely different source text."}])


def test_invalid_page_type_still_rejected():
    with pytest.raises(ValidationError):
        extract(record(source_page="9"), [{"page_number": 8, "text": CLAUSE}])


def test_missing_review_flag_still_rejected():
    item = record()
    item.pop("needs_review")
    with pytest.raises(ValidationError):
        extract(item, [{"page_number": 8, "text": CLAUSE}])


def test_unverified_multi_page_match_does_not_invent_reference():
    input_pages = [{"page_number": 5, "text": CLAUSE}, {"page_number": 6, "text": CLAUSE}]
    data = raw(record(source_page=99))
    assert reconcile_source_pages(data, input_pages) == data
