from app.requirement_relevance import partition_requirements
from app.requirement_schema import (
    RequirementExtractionResult,
    SourceEvidence,
    SourceTrace,
    TenderRequirement,
)


def candidate(
    text: str,
    *,
    mandatory: bool | None = False,
    category: str = "technical",
    status: str = "matched",
    needs_review: bool = False,
) -> TenderRequirement:
    evidence = []
    verified_page = None
    if status == "matched":
        verified_page = 1
        evidence = [
            SourceEvidence(
                page_number=1,
                text=text,
                start_char=0,
                end_char=len(text),
            )
        ]
    return TenderRequirement(
        requirement_text=text,
        category=category,
        mandatory=mandatory,
        source_page=1,
        evidence_needed=None,
        needs_review=needs_review,
        source_trace=SourceTrace(
            original_source_page=1,
            status=status,
            verified_source_page=verified_page,
            evidence=evidence,
        ),
    )


def partition(*items: TenderRequirement):
    return partition_requirements(RequirementExtractionResult(requirements=list(items)))


def test_clear_background_and_definition_candidates_are_excluded():
    result = partition(
        candidate("The project was constructed in 1998."),
        candidate("The term Owner means the contracting authority."),
    )

    assert result.requirements == []
    assert result.review_queue == []
    assert [item.reason for item in result.excluded] == [
        "background_or_history",
        "definition_or_explanation",
    ]


def test_background_mislabeled_mandatory_is_sent_to_review():
    result = partition(
        candidate("The project was constructed in 1998.", mandatory=True),
        candidate("The owner is seeking HVAC design services.", mandatory=True),
    )

    assert result.requirements == []
    assert result.excluded == []
    assert len(result.review_queue) == 2
    assert all(
        "mandatory flag conflicts with apparently non-actionable context"
        in item.reasons
        for item in result.review_queue
    )


def test_procurement_description_without_conflict_is_excluded():
    result = partition(
        candidate("The district is seeking HVAC design services.", mandatory=False)
    )

    assert result.review_queue == []
    assert result.excluded[0].reason == "procurement_description"


def test_mandatory_optional_and_distinct_obligations_are_not_removed():
    mandatory = candidate("The bidder shall submit the equipment schedule.", mandatory=True)
    optional = candidate("Attendance at the site visit is optional.", mandatory=False)
    second = candidate("The bidder must provide warranty information.", mandatory=True)

    result = partition(mandatory, optional, second)

    assert result.requirements == [mandatory, second]
    assert result.review_queue == []
    assert result.excluded == []
    assert result.notices[0].requirement_text == optional.requirement_text
    assert result.notices[0].mandatory is False
    assert result.notices[0].reason == "optional_prebid_event"


def test_genuine_mandatory_obligation_overrides_background_shape():
    obligation = candidate(
        "The project requires the bidder to submit an equipment schedule.",
        mandatory=True,
    )

    result = partition(obligation)

    assert result.requirements == [obligation]
    assert result.review_queue == []
    assert result.excluded == []


def test_conditional_ambiguous_and_unmatched_candidates_are_reviewed():
    conditional = candidate("Additional testing may be required.", mandatory=None)
    unmatched = candidate(
        "The bidder shall provide a schedule.", mandatory=True, status="missing"
    )

    result = partition(conditional, unmatched)

    assert len(result.review_queue) == 2
    assert "mandatory status is uncertain" in result.review_queue[0].reasons
    assert "potentially ambiguous applicability" in result.review_queue[0].reasons
    assert "source quote is missing" in result.review_queue[1].reasons
    assert all(item.requirement.needs_review for item in result.review_queue)


def test_disqualification_unknown_category_and_existing_flags_are_never_excluded():
    disqualification = candidate(
        "Failure to submit the form will disqualify the bidder.",
        mandatory=True,
        category="unknown",
    )
    flagged_background = candidate(
        "The project was constructed in 1998.", needs_review=True
    )

    result = partition(disqualification, flagged_background)

    assert result.requirements == []
    assert len(result.review_queue) == 2
    assert result.excluded == []
    assert "category is unknown" in result.review_queue[0].reasons
    assert "existing review flag" in result.review_queue[1].reasons


def test_partition_does_not_mutate_input_candidate():
    original = candidate("Additional testing may be required.", mandatory=None)

    result = partition(original)

    assert original.needs_review is False
    assert result.review_queue[0].requirement.needs_review is True
    assert result.review_queue[0].requirement is not original


def test_optional_prebid_and_interpretive_definition_are_notices():
    result = partition(
        candidate("The optional pre-bid meeting will be held on Tuesday."),
        candidate('The term "shall" means a mandatory obligation.'),
    )

    assert result.requirements == []
    assert result.review_queue == []
    assert [item.reason for item in result.notices] == [
        "optional_prebid_event",
        "interpretation_definition",
    ]


def test_optional_event_with_real_condition_remains_actionable():
    clause = candidate(
        "The pre-bid meeting is optional, but attendees must register.",
        mandatory=True,
    )

    result = partition(clause)

    assert result.requirements == [clause]
    assert result.notices == []


def test_contact_information_is_notice_but_ambiguous_contact_clause_is_reviewed():
    notice = candidate(
        "Questions may be directed to bids@example.com.",
        category="unknown",
    )
    ambiguous = candidate(
        "Questions may be directed to bids@example.com as applicable.",
        mandatory=None,
    )

    result = partition(notice, ambiguous)

    assert result.notices[0].reason == "contact_information"
    assert result.review_queue[0].requirement == ambiguous.model_copy(
        update={"needs_review": True}
    )
