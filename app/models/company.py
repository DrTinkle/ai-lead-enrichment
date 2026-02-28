from pydantic import BaseModel
from pydantic import Field
from typing import List, Optional


class Company(BaseModel):
    name: str
    industry: Optional[str] = None
    size_estimate: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    raw_summary: Optional[str] = None