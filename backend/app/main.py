from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.llm_client import LLMConfigurationError, completion_client_from_env
from app.pdf_parser import PDFParseError, parse_pdf
from app.tender_analysis import (
    AnalysisInputError,
    TenderAnalysisResponse,
    analyze_parsed_tender,
)

MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MiB
DASHBOARD_PATH = Path(__file__).parent / "static" / "dashboard.html"


app = FastAPI(
    title="HVAC Bid Compliance Copilot API",
    version="0.1.0"
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def review_dashboard():
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@app.post(
    "/tenders/upload",
    responses={
        400: {"description": "Empty PDF file"},
        413: {"description": "PDF exceeds the size limit"},
        415: {"description": "Unsupported or invalid file type"},
        422: {"description": "Unreadable or encrypted PDF"},
    },
)
def upload_tender(file: UploadFile = File(...)):

    filename = file.filename or ""

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported"
        )

    stream = file.file

    file_size = stream.seek(0, 2)
    stream.seek(0)

    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded PDF is empty"
        )

    if file_size > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="PDF exceeds the 20 MiB size limit"
        )

    header = stream.read(5)
    stream.seek(0)

    if header != b"%PDF-":
        raise HTTPException(
            status_code=415,
            detail="Invalid PDF file content"
        )

    try:
        reader = PdfReader(stream)

        if reader.is_encrypted:
            raise HTTPException(
                status_code=422,
                detail="Encrypted PDFs are not supported"
            )

        page_count = len(reader.pages)

    except PyPdfError as exc:
        raise HTTPException(
            status_code=422,
            detail="Unable to read PDF structure"
        ) from exc

    finally:
        stream.seek(0)

    if page_count == 0:
        raise HTTPException(
            status_code=422,
            detail="PDF contains no pages"
        )

    return {
        "filename": filename,
        "filetype": "application/pdf",
        "page_count": page_count,
        "status": "received"
    }

@app.post("/tenders/parse")
async def parse_tender_document(file: UploadFile = File(...)):
    """
    Parse an uploaded tender pdf and return
    extracted text with page numbers.
    """

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(

            status_code=415,

            detail="Only PDF files are supported"

        )

    pdf_bytes = await file.read()

    if len(pdf_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="PDF exceeds the 20 MB size limit"
        )

    if not pdf_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded PDF is empty"
        )

    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=415,
            detail="Invalid PDF file"
        )

    try:

        result = parse_pdf(pdf_bytes)

        return {

            "filename": file.filename,

            **result

        }

    except PDFParseError as exc:

        raise HTTPException(

            status_code=422,

            detail=str(exc)

        )

    finally:

        await file.close()


@app.post(
    "/tenders/analyze",
    response_model=TenderAnalysisResponse,
    responses={
        413: {"description": "Upload or selected text exceeds a safety limit"},
        415: {"description": "Unsupported or invalid file type"},
        422: {"description": "Unreadable PDF or invalid page selection"},
        502: {"description": "Configured LLM request or response failed"},
        503: {"description": "LLM provider is not configured"},
    },
)
def analyze_tender_document(
    file: UploadFile = File(...),
    page_start: int | None = Form(default=None),
    page_end: int | None = Form(default=None),
):
    """Run the existing extraction pipeline with explicit coverage metadata."""

    filename = file.filename or ""
    try:
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=415,
                detail="Only PDF files are supported",
            )

        pdf_bytes = file.file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty")
        if len(pdf_bytes) > MAX_PDF_SIZE:
            raise HTTPException(
                status_code=413,
                detail="PDF exceeds the 20 MiB size limit",
            )
        if not pdf_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=415, detail="Invalid PDF file")

        try:
            parsed = parse_pdf(pdf_bytes)
        except PDFParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            client = completion_client_from_env()
        except LLMConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            return analyze_parsed_tender(
                filename=filename,
                parsed=parsed,
                client=client,
                page_start=page_start,
                page_end=page_end,
            )
        except AnalysisInputError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.detail,
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "LLM provider request failed; verify the configured endpoint "
                    "and provider availability"
                ),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=502,
                detail="LLM response could not be validated",
            ) from exc
    finally:
        file.file.close()
