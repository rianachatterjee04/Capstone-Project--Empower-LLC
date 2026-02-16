from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from .common import ORMBase

class JobCreate(BaseModel):
    title: str
    description: str
    location: str | None = None
    status: str = "draft"

class JobOut(ORMBase):
    id: UUID
    org_id: UUID
    title: str
    description: str
    location: str | None
    status: str
    created_at: datetime

class CandidateCreate(BaseModel):
    job_posting_id: UUID
    full_name: str
    email: EmailStr
    resume_text: str | None = None

class CandidateOut(ORMBase):
    id: UUID
    org_id: UUID
    job_posting_id: UUID
    full_name: str
    email: EmailStr
    resume_text: str | None
    ai_score: int | None
    ai_summary: str | None
    status: str
    created_at: datetime
