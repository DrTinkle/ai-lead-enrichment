from pydantic import BaseModel
from typing import List


class EnrichmentResult(BaseModel):
    summary: str
    sector_classification: str
    maturity_stage: str
    acquisition_fit_score: int
    risk_flags: List[str]
    reasoning: str