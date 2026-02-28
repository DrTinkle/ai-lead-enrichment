from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.services.enrichment import enrich_company
from app.utils.logger import setup_logger

setup_logger()

app = FastAPI(title="Lead Enrichment API")


class AnalyzeRequest(BaseModel):
    domain: str


@app.get("/")
def health():
    # simple health check endpoint
    return {"status": "ok"}


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    domain = request.domain.strip()

    if not domain:
        raise HTTPException(status_code=400, detail="Domain required")

    result = enrich_company(domain)
    return result