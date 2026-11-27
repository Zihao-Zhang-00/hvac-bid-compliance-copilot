"""US-05 contract tests: deterministic evidence, conservative review, integration."""

from copy import deepcopy
from io import BytesIO
import json

import pytest
from reportlab.pdfgen import canvas

from app.pdf_parser import parse_pdf
from app.requirement_extractor import extract_requirements
from app.requirement_provenance import reconcile_source_pages, trace_source_pages
from app.requirement_schema import RequirementExtractionResult, TenderRequirement

CLAUSE = "The units must use R-32 refrigerant."


def record(**changes):
    data = dict(requirement_text=CLAUSE, source_page=1, category="technical",
                mandatory=True, evidence_needed="Manufacturer sheet", needs_review=False)
    data.update(changes)
    return TenderRequirement(**data)


def trace(pages, **changes):
    return trace_source_pages(
        RequirementExtractionResult(requirements=[record(**changes)]), pages,
    ).requirements[0]


class ReplayLLM:
    def __init__(self, data):
        self.data = data

    def complete(self, system_prompt, user_prompt):
        return json.dumps({"requirements": [self.data]})


def test_correct_page_has_exact_evidence_and_offsets():
    source = "Heading\n" + CLAUSE + "\nFooter"
    item = trace([{"page_number": 1, "text": source}])
    assert item.source_trace.status == "matched"
    assert item.source_trace.original_source_page == item.source_trace.verified_source_page == 1
    assert not item.needs_review
    evidence, = item.source_trace.evidence
    assert evidence.text == CLAUSE
    assert evidence.start_char == len("Heading\n")
    assert source[evidence.start_char:evidence.end_char] == evidence.text
    assert evidence.page_number == item.source_page


def test_wrong_page_corrected_and_original_retained_in_pipeline():
    item = extract_requirements(
        [{"page_number": 4, "text": CLAUSE}],
        ReplayLLM(record(source_page=99).model_dump(mode="json")),
    ).requirements[0]
    assert item.source_page == item.source_trace.verified_source_page == 4
    assert item.source_trace.original_source_page == 99
    assert item.needs_review


@pytest.mark.parametrize("reported", [1, 2])
def test_multiple_pages_never_disambiguated_by_model_hint(reported):
    pages = [{"page_number": n, "text": CLAUSE} for n in [2, 1]]
    item = trace(pages, source_page=reported)
    assert item.source_trace.status == "ambiguous"
    assert item.source_trace.verified_source_page is None
    assert item.source_page == reported
    assert [e.page_number for e in item.source_trace.evidence] == [1, 2]
    assert item.needs_review
    integrated = extract_requirements(pages, ReplayLLM(record(source_page=reported).model_dump(mode="json")))
    assert integrated.requirements[0] == item


def test_missing_source_has_no_invented_evidence():
    pages = [{"page_number": 1, "text": "Unrelated heading."}]
    item = extract_requirements(pages, ReplayLLM(record().model_dump(mode="json"))).requirements[0]
    assert item.source_trace.status == "missing"
    assert item.source_trace.verified_source_page is None
    assert item.source_trace.evidence == []
    assert item.source_page == item.source_trace.original_source_page == 1
    assert item.needs_review


@pytest.mark.parametrize("text,quote", [
    ("THE units\t must\n use  R-32 refrigerant.", CLAUSE),
    ("Straße\n  MUST comply.", "STRASSE must comply."),
    ("\tMust\u00a0 comply.\n", "must comply."),
])
def test_normalization_preserves_original_slice(text, quote):
    item = trace([{"page_number": 1, "text": text}], requirement_text=quote)
    assert item.source_trace.status == "matched"
    evidence, = item.source_trace.evidence
    assert evidence.text == text.strip()
    assert evidence.text == text[evidence.start_char:evidence.end_char]
    assert item.requirement_text == quote


@pytest.mark.parametrize("source,quote", [
    ("COP must be at least 5.8.", "COP must be at least 5.9."),
    ("Units must not use R-32.", "Units must use R-32."),
    ("Units must use R-32.", "Units must not use R-32."),
    ("COP 50", "COP 5"),
    ("COP 5.8", "COP 5"),
    ("COP 5.8", "COP 5."),
    ("5.8 kW", "8 kW"),
    ("COP 5,800", "COP 5"),
    ("Notrequired", "required"),
    ("Requiredness", "Required"),
    ("ß", "s"),
    ("Do A.\nDo B.", "Do A and B."),
])
def test_key_differences_and_partial_tokens_not_confirmed(source, quote):
    item = trace([{"page_number": 1, "text": source}], requirement_text=quote)
    assert item.source_trace.status == "missing"
    assert item.source_trace.evidence == []
    assert item.needs_review


def test_one_page_multiple_occurrences_retains_all_evidence():
    text = CLAUSE + "\n" + CLAUSE
    item = trace([{"page_number": 1, "text": text}])
    assert item.source_trace.status == "matched"
    assert [e.start_char for e in item.source_trace.evidence] == [0, len(CLAUSE) + 1]


@pytest.mark.parametrize("text", [CLAUSE, "Missing"])
def test_existing_review_and_unrelated_fields_preserved_without_mutation(text):
    original = RequirementExtractionResult(requirements=[record(needs_review=True)])
    before = original.model_dump()
    pages = [{"page_number": 2, "text": text}]
    pages_before = deepcopy(pages)
    output = trace_source_pages(original, pages)
    item = output.requirements[0]
    assert item.needs_review
    for name in ["requirement_text", "category", "mandatory", "evidence_needed"]:
        assert getattr(item, name) == getattr(original.requirements[0], name)
    assert original.model_dump() == before
    assert pages == pages_before
    assert item is not original.requirements[0]
    assert trace_source_pages(output, pages) == output
    assert RequirementExtractionResult.model_validate_json(output.model_dump_json()) == output


def test_recomputation_does_not_trust_stale_trace():
    result = RequirementExtractionResult(requirements=[trace([{"page_number": 2, "text": CLAUSE}])])
    changed = trace_source_pages(result, [{"page_number": 1, "text": "Different document"}])
    assert changed.requirements[0].source_trace.status == "missing"
    assert changed.requirements[0].source_trace.evidence == []
    assert changed.requirements[0].source_page == 1
    assert result.requirements[0].source_trace.status == "matched"


def test_model_cannot_forge_trace_or_original_page():
    data = record().model_dump(mode="json")
    data["source_trace"] = {"status": "matched", "original_source_page": 777,
                            "verified_source_page": 777, "evidence": "fabricated"}
    result = extract_requirements([{"page_number": 1, "text": "Missing"}], ReplayLLM(data))
    assert result.requirements[0].source_trace.original_source_page == 1
    assert result.requirements[0].source_trace.status == "missing"


def test_untraced_old_schema_serializes_unchanged():
    assert "source_trace" not in record().model_dump()
    assert record().source_trace is None


@pytest.mark.parametrize("pages", [
    [{"page_number": True, "text": "text"}],
    [{"page_number": 0, "text": "text"}],
    [{"page_number": 1, "text": "text"}, {"page_number": 1, "text": "text"}],
    [{"page_number": 1, "text": None}],
])
def test_standalone_tracing_rejects_invalid_page_identity(pages):
    with pytest.raises(ValueError):
        trace(pages)


def test_empty_pages_and_empty_results():
    assert trace([]).source_trace.status == "missing"
    assert trace_source_pages(RequirementExtractionResult(requirements=[]), []).requirements == []


def test_recovery_leaves_malformed_payload_to_validator():
    assert reconcile_source_pages("[]", []) == "[]"
    assert reconcile_source_pages('{"requirements": [null]}', []) == '{"requirements": [null]}'


def test_pdf_bytes_parse_extract_trace_with_replayed_model():
    """Actual synthetic PDF parsing, explicitly not a live-model E2E test."""
    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 700, "Synthetic tender cover")
    pdf.showPage()
    pdf.drawString(72, 700, CLAUSE)
    pdf.save()
    parsed = parse_pdf(stream.getvalue())
    assert parsed["page_count"] == 2
    item = extract_requirements(parsed["pages"], ReplayLLM(record().model_dump(mode="json"))).requirements[0]
    assert item.source_trace.original_source_page == 1
    assert item.source_trace.verified_source_page == 2
    evidence, = item.source_trace.evidence
    assert evidence.text == CLAUSE
    assert parsed["pages"][1]["text"][evidence.start_char:evidence.end_char] == CLAUSE
