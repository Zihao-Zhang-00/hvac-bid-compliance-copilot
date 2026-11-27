import csv
import json
from io import BytesIO

import pytest
from reportlab.pdfgen import canvas

from app.dataset_audit import (
    infer_document_role,
    infer_project_metadata,
    inventory_dataset,
    main,
    make_document_id,
    write_audit_outputs,
)


def make_pdf(path, page_texts):
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    for text in page_texts:
        if text:
            document.drawString(72, 720, text)
        document.showPage()
    document.save()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())


def test_inventory_handles_unicode_nested_paths_and_page_statistics(tmp_path):
    catalog = tmp_path / "厂家技术手册" / "Carrier" / "产品目录.pdf"
    make_pdf(catalog, ["A" * 80, "", "short"])
    spreadsheet = tmp_path / "tenders" / "nwacc_2026" / "bid_schedule.XLSX"
    spreadsheet.parent.mkdir(parents=True)
    spreadsheet.write_bytes(b"synthetic spreadsheet fixture")
    (tmp_path / "ignore.txt").write_text("unsupported", encoding="utf-8")

    documents = inventory_dataset(tmp_path)

    assert [item["relative_path"] for item in documents] == [
        "tenders/nwacc_2026/bid_schedule.XLSX",
        "厂家技术手册/Carrier/产品目录.pdf",
    ]
    pdf = documents[1]
    assert pdf["document_role"] == "manufacturer catalog"
    assert pdf["pdf_page_count"] == 3
    assert pdf["extractable_text_pages"] == [1, 3]
    assert pdf["empty_pages"] == [2]
    assert pdf["low_text_pages"] == [3]
    assert pdf["parsing_failure"] is None
    assert len(pdf["sha256"]) == 64
    assert pdf["project_group"] == "manufacturer_catalogs"
    assert pdf["dataset_split"] is None
    assert documents[0]["document_role"] == "spreadsheet"
    assert documents[0]["project_group"] == "nwacc_2026"
    assert documents[0]["dataset_split"] == "development"


def test_malformed_pdf_is_recorded_without_stopping_inventory(tmp_path):
    malformed = tmp_path / "tenders" / "glendale_2026" / "broken.pdf"
    malformed.parent.mkdir(parents=True)
    malformed.write_bytes(b"not a pdf")

    document = inventory_dataset(tmp_path)[0]

    assert document["document_role"] == "tender"
    assert document["pdf_page_count"] is None
    assert document["extractable_text_pages"] == []
    assert document["parsing_failure"].startswith("Unable to parse PDF (")


@pytest.mark.parametrize(
    ("relative_path", "file_type", "expected"),
    [
        ("tenders/nwacc_2026/Addendum 2.pdf", "pdf", "addendum"),
        ("tenders/glendale_2026/Mechanical Plans.pdf", "pdf", "drawing"),
        ("tenders/worcester_2026/HVAC Permit Set.pdf", "pdf", "drawing"),
        ("tenders/worcester_2026/AHU Redesign.pdf", "pdf", "drawing"),
        ("misc/Redesign notes.pdf", "pdf", "unknown"),
        ("tenders/worcester_2026/Bid Tabulation.pdf", "pdf", "bid result"),
        ("tenders/worcester_2026/Invitation.pdf", "pdf", "tender"),
        ("misc/ambiguous.pdf", "pdf", "unknown"),
        ("misc/results.xlsx", "xlsx", "spreadsheet"),
    ],
)
def test_role_inference_is_conservative(relative_path, file_type, expected):
    assert infer_document_role(relative_path, file_type) == expected


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("tenders/nwacc_2026/Tender.pdf", ("nwacc_2026", "development")),
        (
            "tenders/glendale_2026/Addendum.pdf",
            ("glendale_2026", "validation"),
        ),
        (
            "tenders/worcester_2026/Permit Set.pdf",
            ("worcester_2026", "held_out"),
        ),
        ("厂家技术手册/Carrier/Catalog.pdf", ("manufacturer_catalogs", None)),
        ("misc/ambiguous.pdf", ("unknown", None)),
    ],
)
def test_project_metadata_uses_document_level_splits(relative_path, expected):
    assert infer_project_metadata(relative_path) == expected


def test_outputs_are_reproducible_and_annotation_template_is_blank(tmp_path):
    make_pdf(tmp_path / "tenders" / "nwacc_2026" / "Tender.pdf", ["B" * 80])
    documents = inventory_dataset(tmp_path)

    first = write_audit_outputs(documents, tmp_path / "first")
    second = write_audit_outputs(documents, tmp_path / "second")

    for key in ("json", "csv", "summary", "annotations"):
        assert first[key].read_bytes() == second[key].read_bytes()

    payload = json.loads(first["json"].read_text(encoding="utf-8"))
    assert payload["summary"]["document_count"] == 1
    assert payload["summary"]["parsing_failure_count"] == 0
    assert payload["documents"][0]["project_group"] == "nwacc_2026"
    assert payload["documents"][0]["dataset_split"] == "development"
    assert "B" * 80 not in first["json"].read_text(encoding="utf-8")

    with first["csv"].open(encoding="utf-8", newline="") as source:
        inventory_row = next(csv.DictReader(source))
    assert inventory_row["project_group"] == "nwacc_2026"
    assert inventory_row["dataset_split"] == "development"

    with first["annotations"].open(encoding="utf-8", newline="") as source:
        assert list(csv.reader(source)) == [
            [
                "requirement_id",
                "document_id",
                "exact_quote",
                "source_page",
                "relevance_label",
                "obligation_status",
                "category",
                "evidence_required",
                "reviewer_notes",
            ]
        ]


def test_cli_writes_default_outputs_and_prints_summary(tmp_path, capsys):
    make_pdf(tmp_path / "tenders" / "nwacc_2026" / "Tender.pdf", ["C" * 80])

    assert main(["--dataset-root", str(tmp_path)]) == 0

    output_dir = tmp_path / "dataset-audit-output"
    assert (output_dir / "inventory.json").is_file()
    assert (output_dir / "inventory.csv").is_file()
    assert (output_dir / "audit_summary.txt").is_file()
    assert (output_dir / "requirement_annotations_template.csv").is_file()
    assert "Documents: 1" in capsys.readouterr().out


def test_document_id_is_unicode_normalized_and_path_specific():
    composed = "厂家技术手册/Caf\N{LATIN SMALL LETTER E WITH ACUTE}.pdf"
    decomposed = "厂家技术手册/Cafe\N{COMBINING ACUTE ACCENT}.pdf"

    assert make_document_id(composed) == make_document_id(decomposed)
    assert make_document_id(composed) != make_document_id("other/file.pdf")


def test_invalid_root_and_threshold_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="not a directory"):
        inventory_dataset(tmp_path / "missing")
    with pytest.raises(ValueError, match="at least 1"):
        inventory_dataset(tmp_path, low_text_threshold=0)
