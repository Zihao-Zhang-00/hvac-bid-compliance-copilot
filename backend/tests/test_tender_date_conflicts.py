from app.tender_date_conflicts import detect_date_conflicts


def test_same_event_conflicting_cover_and_timetable_dates_are_flagged():
    pages = [
        {"page_number": 1, "text": "Bid submission deadline: May 1, 2026 at 2:00 PM"},
        {"page_number": 3, "text": "Bid due date: May 2, 2026 at 2:00 PM"},
    ]

    conflicts = detect_date_conflicts(pages)

    assert len(conflicts) == 1
    assert conflicts[0].event_type == "bid_submission_deadline"
    assert conflicts[0].conflicting_values == [
        "2026-05-01 14:00",
        "2026-05-02 14:00",
    ]
    assert conflicts[0].source_pages == [1, 3]
    assert conflicts[0].status == "review_required"
    assert conflicts[0].evidence[0].exact_text.startswith("Bid submission")


def test_different_milestones_and_duplicate_equivalent_dates_do_not_conflict():
    pages = [
        {
            "page_number": 1,
            "text": (
                "Bid due date: May 1, 2026 at 2:00 PM\n"
                "Bid opening date: May 1, 2026 at 3:00 PM\n"
                "Question deadline: April 20, 2026"
            ),
        },
        {"page_number": 2, "text": "Bid submission deadline: 05/01/2026 2:00 PM"},
    ]

    assert detect_date_conflicts(pages) == []


def test_tentative_same_event_difference_is_reported_as_uncertain():
    pages = [
        {"page_number": 1, "text": "Anticipated bid opening date: June 1, 2026"},
        {"page_number": 2, "text": "Bid opening date: June 2, 2026"},
    ]

    conflicts = detect_date_conflicts(pages)

    assert conflicts[0].reason == "tentative_or_amended_values"
    assert conflicts[0].evidence[0].tentative is True


def test_ambiguous_date_label_is_not_invented_as_an_event():
    pages = [
        {"page_number": 1, "text": "Important date: July 1, 2026"},
        {"page_number": 2, "text": "Project calendar: July 2, 2026"},
    ]

    assert detect_date_conflicts(pages) == []


def test_less_precise_duplicate_date_is_not_treated_as_a_conflict():
    pages = [
        {"page_number": 1, "text": "Question deadline: August 1, 2026"},
        {"page_number": 2, "text": "Question deadline: August 1, 2026 at 5:00 PM"},
    ]

    assert detect_date_conflicts(pages) == []
