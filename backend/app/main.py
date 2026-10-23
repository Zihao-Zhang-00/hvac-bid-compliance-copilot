
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from pypdf import PdfReader
from pypdf.errors import PyPdfError


MAX_PDF_SIZE = 20 * 1024 * 1024  # 20 MiB


app = FastAPI(
    title="HVAC Bid Compliance Copilot API",
    version="0.1.0"
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


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
