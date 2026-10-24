from io import BytesIO
from pypdf import PdfReader

class PDFParseError(Exception):
    """Raised when a PDF cannot be parsed."""

def parse_pdf(pdf_bytes: bytes) -> dict:
    """
    Extracts text from a PDF  while preserving page numbers.
    """

    if not pdf_bytes:
        raise PDFParseError("PDF file is empty.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes))

        if reader.is_encrypted:
            raise PDFParseError(
                "Encrypted PDFs are not supported."
            )

        if len(reader.pages) == 0:
            raise PDFParseError(
                "PDF contains no pages."
                )

        pages = []

        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""

            pages.append({
                "page_number": index + 1,
                "text": text.strip()
            })

        return {
            "page_count": len(pages),
            "pages": pages,
            "status": "parsed"
            }

    except PDFParseError:
        raise
    except Exception as exc:
        raise PDFParseError(
           "Unable to parse PDF document"
        ) from exc