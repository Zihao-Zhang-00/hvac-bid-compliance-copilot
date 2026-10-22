
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from pypdf import PdfReader
from pypdf.errors import PdfReadError

app = FastAPI(
    title="HVAC Bid Compliance Copilot API",
    version="0.1.0"
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/tenders/upload")
def upload_tender(file: UploadFile = File(...)):

    filename = file.filename or ""

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported"
        )

    stream = file.file
    header = stream.read(5)
    stream.seek(0)

    if header != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid PDF file content"
        )

    try:
        reader = PdfReader(stream)

        if reader.is_encrypted:
            raise HTTPException(
                status_code=422,
                detail="Encrypted PDF files are not supported"
            )

        page_count = len(reader.pages)

    except PdfReadError:
        raise HTTPException(
            status_code=422,
            detail="Unable to read PDF structure"
        )

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
