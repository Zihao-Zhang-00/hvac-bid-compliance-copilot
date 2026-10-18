from fastapi import FastAPI
app = FastAPI(
    title = "HVAC Bid Compliance Copilot API",
    version = "0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}