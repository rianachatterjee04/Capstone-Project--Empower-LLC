from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from .common import ORMBase

class ReviewCreate(BaseModel):
    employee_id: UUID
    cycle: str

class ReviewSubmit(BaseModel):
    self_review: dict | None = None
    manager_review: dict | None = None
    status: str | None = None  # draft/submitted/finalized

class ReviewOut(ORMBase):
    id: UUID
    org_id: UUID
    employee_id: UUID
    cycle: str
    self_review: dict
    manager_review: dict
    ai_flags: dict
    status: str
    created_at: datetime
