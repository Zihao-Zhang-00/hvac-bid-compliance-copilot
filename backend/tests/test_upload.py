
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.main import app, MAX_PDF_SIZE


client = TestClient(app)


def create_test_pdf(page_count=2, encrypted=False):
    writer = PdfWriter()

    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)

    if encrypted:
        writer.encrypt("test-password")

    buffer = BytesIO()
    writer.write(buffer)

    return buffer.getvalue()


def test_successful_pdf_upload():
    pdf_data = create_test_pdf(page_count=2)

    response = client.post(
        "/tenders/upload",
        files={"file": ("sample.pdf", pdf_data, "application/pdf")}
    )

    assert response.status_code == 200
    assert response.json() == {
        "filename": "sample.pdf",
        "filetype": "application/pdf",
        "page_count": 2,
        "status": "received"
    }


def test_unsupported_file_extension():
    response = client.post(
        "/tenders/upload",
        files={"file": ("notes.txt", b"Hello", "text/plain")}
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only PDF files are supported"


def test_fake_pdf_content():
    response = client.post(
        "/tenders/upload",
        files={"file": ("fake.pdf", b"Hello", "application/pdf")}
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Invalid PDF file content"


def test_empty_pdf():
    response = client.post(
        "/tenders/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded PDF is empty"


def test_corrupted_pdf():
    invalid_data = b"%PDF-1.7\nThis is not a complete PDF."

    response = client.post(
        "/tenders/upload",
        files={"file": ("corrupted.pdf", invalid_data, "application/pdf")}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unable to read PDF structure"


def test_oversized_pdf():
    large_data = b"x" * (MAX_PDF_SIZE + 1)

    response = client.post(
        "/tenders/upload",
        files={"file": ("large.pdf", large_data, "application/pdf")}
    )

    assert response.status_code == 413
    assert "size limit" in response.json()["detail"]


def test_encrypted_pdf():
    pdf_data = create_test_pdf(encrypted=True)

    response = client.post(
        "/tenders/upload",
        files={"file": ("encrypted.pdf", pdf_data, "application/pdf")}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Encrypted PDFs are not supported"


def test_missing_upload_file():
    response = client.post("/tenders/upload")

    assert response.status_code == 422


def test_zero_page_pdf():
    pdf_data = create_test_pdf(page_count=0)

    response = client.post(
        "/tenders/upload",
        files={"file": ("zero-pages.pdf", pdf_data, "application/pdf")}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "PDF contains no pages"



def test_api_recovers_after_invalid_upload():
    bad_response = client.post(
        "/tenders/upload",
        files={"file": ("invalid.pdf", b"Hello", "application/pdf")}
    )

    assert bad_response.status_code == 415

    good_response = client.post(
        "/tenders/upload",
        files={
            "file": ("valid.pdf", create_test_pdf(1), "application/pdf")
        }
    )

    assert good_response.status_code == 200
    assert good_response.json()["page_count"] == 1

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
