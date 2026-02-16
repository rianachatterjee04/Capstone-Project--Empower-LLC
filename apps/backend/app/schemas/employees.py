from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from .common import ORMBase

class EmployeeInvite(BaseModel):
    employee_number: str
    legal_name: str
    preferred_name: str | None = None
    email: EmailStr
    job_title: str | None = None
    department: str | None = None
    location: str | None = None

class EmployeeOut(ORMBase):
    id: UUID
    org_id: UUID
    user_id: str | None
    employee_number: str
    legal_name: str
    preferred_name: str | None
    email: EmailStr
    status: str
    job_title: str | None
    department: str | None
    location: str | None
    created_at: datetime
