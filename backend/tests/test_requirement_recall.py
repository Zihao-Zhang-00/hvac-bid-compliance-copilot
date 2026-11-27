from app.requirement_recall import find_uncovered_critical_passages
from app.requirement_schema import RequirementExtractionResult, TenderRequirement


def extracted(text):
    return TenderRequirement(
        requirement_text=text,
        category="technical",
        mandatory=True,
        source_page=1,
        evidence_needed=None,
        needs_review=False,
    )


def test_uncovered_brand_and_response_instructions_become_exact_review_candidates():
    text = (
        "Carrier or an approved substitute is acceptable. "
        "Do not provide responses unless expressly requested."
    )
    pages = [{"page_number": 1, "text": text}]

    candidates = find_uncovered_critical_passages(
        pages,
        RequirementExtractionResult(requirements=[]),
    )

    assert len(candidates) == 2
    assert all(item.needs_review and item.mandatory is None for item in candidates)
    for item in candidates:
        evidence = item.source_trace.evidence[0]
        assert text[evidence.start_char:evidence.end_char] == item.requirement_text
        assert item.source_trace.verified_source_page == 1


def test_conditional_approval_and_technical_threshold_are_preserved_for_review():
    pages = [{
        "page_number": 1,
        "text": (
            "Alternatives require an approved equal before bidding. "
            "Minimum airflow is 1200 CFM."
        ),
    }]

    candidates = find_uncovered_critical_passages(
        pages,
        RequirementExtractionResult(requirements=[]),
    )

    assert [item.requirement_text for item in candidates] == [
        "Alternatives require an approved equal before bidding.",
        "Minimum airflow is 1200 CFM.",
    ]


def test_already_extracted_exact_passage_is_not_duplicated():
    quote = "The contractor must be licensed in this state."

    candidates = find_uncovered_critical_passages(
        [{"page_number": 1, "text": quote}],
        RequirementExtractionResult(requirements=[extracted(quote)]),
    )

    assert candidates == []
