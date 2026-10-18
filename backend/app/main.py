from fastapi import FastAPI, File, UploadFile

app = FastAPI(
    title="HVAC Bid Compliance Copilot API",
    version="0.1.0"
)

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/tenders/upload")
async def upload_tender(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "status": "received"
    }