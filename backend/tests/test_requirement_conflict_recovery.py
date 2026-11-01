"""Safety tests for conflicting duplicate requirements in US-03."""
import json

import pytest
from pydantic import ValidationError

from app.requirement_validation import validate_and_normalize_requirements


def requirement(**kwargs):
    item = dict(
        requirement_text="• Proposed preventive maintenance visit schedule",
        category="scoring",
        mandatory=False,
        source_page=7,
        evidence_needed=None,
        needs_review=False,
    )
    item.update(kwargs)
    return item


def extract(items, pages=None):
    if pages is None:
        pages = {7}
    return validate_and_normalize_requirements(
        json.dumps({"requirements": items}), pages
    ).requirements


def test_conflicting_categories_keep_agreed_mandatory_and_evidence(caplog):
    a = requirement(category="personnel", mandatory=True,
                    evidence_needed="Personnel record")
    b = requirement(category="documentation", mandatory=True,
                    evidence_needed="Personnel record")
    with caplog.at_level("WARNING"):
        result = extract([a, b])
    assert len(result) == 1
    assert result[0].category.value == "unknown"
    assert result[0].mandatory is True
    assert result[0].evidence_needed == "Personnel record"
    assert result[0].needs_review is True
    assert "Conflicting duplicate" in caplog.text


def test_conflicting_category_mandatory_and_evidence_are_quarantined():
    a = requirement()
    b = requirement(category="documentation", mandatory=True,
                    evidence_needed="Schedule document")
    result = extract([a, b])
    assert len(result) == 1
    assert result[0].requirement_text == a["requirement_text"]
    assert result[0].source_page == 7
    assert result[0].category.value == "unknown"
    assert result[0].mandatory is None
    assert result[0].evidence_needed is None
    assert result[0].needs_review is True


def test_conflicting_evidence_only_preserves_agreed_category_and_mandatory():
    a = requirement(category="personnel", mandatory=True,
                    evidence_needed=None)
    b = requirement(category="personnel", mandatory=True,
                    evidence_needed="Technician list")
    item = extract([a, b])[0]
    assert item.category.value == "personnel"
    assert item.mandatory is True
    assert item.evidence_needed is None
    assert item.needs_review is True


def test_identical_duplicates_remain_unflagged():
    a = requirement()
    items = extract([a, dict(a)])
    assert len(items) == 1
    assert items[0].category.value == "scoring"
    assert items[0].needs_review is False


def test_multiple_conflicts_do_not_resolve_back_to_an_arbitrary_value():
    a = requirement(category="personnel", mandatory=True)
    b = requirement(category="documentation", mandatory=False)
    c = requirement(category="personnel", mandatory=True)
    item = extract([a, b, c])[0]
    assert item.category.value == "unknown"
    assert item.mandatory is None
    assert item.needs_review is True


def test_same_quote_different_page_not_merged():
    a = requirement(source_page=7)
    b = requirement(source_page=8)
    items = extract([a, b], {7, 8})
    assert len(items) == 2
    assert {item.source_page for item in items} == {7, 8}


def test_invalid_schema_not_quarantined_as_duplicate():
    with pytest.raises(ValidationError):
        extract([requirement(source_page="7"), requirement()])


def test_out_of_input_source_page_still_rejected():
    with pytest.raises(ValueError, match="source page"):
        extract([requirement(source_page=99)])
