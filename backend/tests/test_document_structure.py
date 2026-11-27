from app.document_structure import build_extraction_view


def test_masks_repeated_headers_page_labels_and_navigation_without_changing_offsets():
    pages = [
        {
            "page_number": 1,
            "text": (
                "HVAC PROCUREMENT 2026\n"
                "Meaningful introduction at the top boundary.\n"
                "Item | Bidder shall submit a bid bond.\n"
                "Page 1 of 2"
            ),
        },
        {
            "page_number": 2,
            "text": (
                "HVAC PROCUREMENT 2026\n"
                "1 GENERAL INFORMATION\n"
                "Meaningful warranty text near the bottom boundary.\n"
                "Page 2 of 2"
            ),
        },
    ]

    masked = build_extraction_view(pages)

    assert [len(item["text"]) for item in masked] == [
        len(item["text"]) for item in pages
    ]
    assert "HVAC PROCUREMENT 2026" not in masked[0]["text"]
    assert "Page 1 of 2" not in masked[0]["text"]
    assert "1 GENERAL INFORMATION" not in masked[1]["text"]
    assert "Bidder shall submit a bid bond." in masked[0]["text"]
    assert "Meaningful introduction at the top boundary." in masked[0]["text"]
    assert "Meaningful warranty text near the bottom boundary." in masked[1]["text"]


def test_repeated_substantive_table_obligation_is_not_masked():
    obligation = "Equipment | Contractor must provide 10-year warranty"
    pages = [
        {"page_number": 1, "text": f"{obligation}\nPage 1"},
        {"page_number": 2, "text": f"{obligation}\nPage 2"},
    ]

    masked = build_extraction_view(pages)

    assert all(obligation in item["text"] for item in masked)


def test_brand_constraint_that_looks_like_a_heading_is_preserved():
    text = "TRANE OR APPROVED SUBSTITUTE\n2"

    masked = build_extraction_view([{"page_number": 2, "text": text}])

    assert masked[0]["text"].startswith("TRANE OR APPROVED SUBSTITUTE")
