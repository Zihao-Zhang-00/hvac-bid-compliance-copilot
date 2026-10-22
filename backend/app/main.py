from fastapi import FastAPI, File, UploadFile, HTTPException, status

app = FastAPI(
    title="HVAC Bid Compliance Copilot API",
    version="0.1.0"
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/tenders/upload")
async def upload_tender(file: UploadFile = File(...)):

    filename = file.filename or ""

    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported"
        )

    header = await file.read(5)
    await file.seek(0)

    if header != b"%PDF-":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid PDF file content"
        )

    return {
        "filename": filename,
        "status": "received"
    }
