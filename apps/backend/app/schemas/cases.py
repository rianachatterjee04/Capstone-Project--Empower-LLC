from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from .common import ORMBase

class CaseCreate(BaseModel):
    category: str
    severity: str = "medium"
    details: str
    is_anonymous: bool = True
    reporter_employee_id: UUID | None = None

class CaseOut(ORMBase):
    id: UUID
    org_id: UUID
    reporter_employee_id: UUID | None
    is_anonymous: bool
    category: str
    severity: str
    details: str
    status: str
    escalation_level: int
    last_action_at: datetime
    created_at: datetime

class CaseAction(BaseModel):
    action: str  # acknowledge/assign/escalate/resolve
    note: str | None = None
