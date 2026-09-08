from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class JobRequirementBase(BaseModel):
    category: str  # 'mandatory', 'desirable', 'experience', 'competency'
    title: str
    weight: float = 1.0

class JobRequirementCreate(JobRequirementBase):
    pass

class JobRequirementResponse(JobRequirementBase):
    id: int
    class Config:
        from_attributes = True

class JobCreate(BaseModel):
    title: str
    description: str
    requirements: List[JobRequirementCreate] = []

class JobCreateFromSource(BaseModel):
    title: str
    source_type: str # 'url', 'text'
    job_url: Optional[str] = None
    description_text: Optional[str] = None

class JobResponse(BaseModel):
    id: int
    title: str
    description: str
    created_at: datetime
    class Config:
        from_attributes = True


class ScreeningResultResponse(BaseModel):
    id: int
    candidate_name: str
    name: str
    score: float
    mandatory_matched: str
    experience: str
    status: str
    evidences: Optional[dict] = None

class ScreeningSummaryResponse(BaseModel):
    total_candidates: int
    high_match_count: int
    results: List[ScreeningResultResponse]
