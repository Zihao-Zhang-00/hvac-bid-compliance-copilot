from io import BytesIO

import pytest
from app.main import app
from app.pdf_parser import PDFParseError, parse_pdf
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

client = TestClient(app)

def create_test_pdf(page_count=2, encrypted=False):
    """Create a synthetic PDF for testing"""

    writer = PdfWriter()

    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)

    if encrypted:
        writer.encrypt("test-password")

    buffer = BytesIO()
    writer.write(buffer)

    return buffer.getvalue()

def test_parse_single_page():
    pdf_data = create_test_pdf(page_count=1)
    result = parse_pdf(pdf_data)
    assert result["page_count"] == 1
    assert len(result["pages"]) == 1
    assert result["pages"][0]["page_number"] == 1
    assert result["status"] == "parsed"



def test_parse_multiple_pages():

    pdf_data = create_test_pdf(3)

    result = parse_pdf(pdf_data)

    assert result["page_count"] == 3

    assert len(result["pages"]) == 3

    for index, page in enumerate(result["pages"]):

        assert page["page_number"] == index + 1

def test_empty_pdf():

    with pytest.raises(

        PDFParseError,

        match="PDF file is empty"

    ):

        parse_pdf(b"")

def test_invalid_pdf():

    with pytest.raises(PDFParseError):

        parse_pdf(b"This is not a PDF")

def test_encrypted_pdf():

    pdf_data = create_test_pdf(encrypted=True)

    with pytest.raises(

        PDFParseError,

        match="Encrypted PDFs are not supported"

    ):

        parse_pdf(pdf_data)

def test_zero_page_pdf():

    pdf_data = create_test_pdf(0)

    with pytest.raises(

        PDFParseError,

        match="PDF contains no pages"

    ):

        parse_pdf(pdf_data)    


def test_extract_real_text():
    buffer = BytesIO()

    pdf = canvas.Canvas(buffer)

    pdf.drawString(
        100,
        700,
        "HVAC Tender Technical Requirements"
    )

    pdf.drawString(
        100,
        670,
        "Cooling Capacity: 500 kW"
    )

    pdf.showPage()

    pdf.drawString(
        100,
        700,
        "Required Certification: ISO 9001"
    )

    pdf.save()

    result = parse_pdf(buffer.getvalue())

    assert result["page_count"] == 2

    assert (
        "HVAC Tender Technical Requirements"
        in result["pages"][0]["text"]
    )

    assert (
        "Cooling Capacity: 500 kW"
        in result["pages"][0]["text"]
    )

    assert (
        "Required Certification: ISO 9001"
        in result["pages"][1]["text"]
    )

    assert result["pages"][0]["page_number"] == 1
    assert result["pages"][1]["page_number"] == 2        


def test_parse_api_success():
    pdf_data = create_test_pdf(2)

    response = client.post(
        "/tenders/parse",
        files={
            "file": (
                "tender.pdf",
                pdf_data,
                "application/pdf"
            )
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["filename"] == "tender.pdf"
    assert data["page_count"] == 2
    assert len(data["pages"]) == 2


def test_parse_api_reject_txt():
    response = client.post(
        "/tenders/parse",
        files={
            "file": (
                "notes.txt",
                b"Not a PDF",
                "text/plain"
            )
        }
    )

    assert response.status_code == 415


def test_parse_api_reject_fake_pdf():
    response = client.post(
        "/tenders/parse",
        files={
            "file": (
                "fake.pdf",
                b"Hello World",
                "application/pdf"
            )
        }
    )

    assert response.status_code == 415


def test_parse_api_empty_file():
    response = client.post(
        "/tenders/parse",
        files={
            "file": (
                "empty.pdf",
                b"",
                "application/pdf"
            )
        }
    )

    assert response.status_code == 400   

def test_parse_api_corrupted_pdf():
    response = client.post(
        "/tenders/parse",
        files={
            "file": (
                "corrupted.pdf",
                b"%PDF-1.7\nThis is not a valid PDF",
                "application/pdf"
            )
        }
    )

    assert response.status_code == 422
    assert "detail" in response.json()