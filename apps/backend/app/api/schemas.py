from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Dict, List
from uuid import UUID
from datetime import datetime

class EmployeeOut(BaseModel):
    id: UUID
    org_id: UUID
    user_id: Optional[UUID] = None
    employee_number: Optional[str] = None
    legal_name: str
    preferred_name: Optional[str] = None
    email: str
    status: str
    job_title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    manager_employee_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

class EmployeeCreate(BaseModel):
    legal_name: str
    email: str
    preferred_name: Optional[str] = None
    employee_number: Optional[str] = None
    status: str = "invited"
    job_title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    manager_employee_id: Optional[UUID] = None

class OnboardingPacketOut(BaseModel):
    id: UUID
    org_id: UUID
    employee_id: UUID
    status: str
    requested_items: Dict[str, Any] = Field(default_factory=dict)
    submitted_items: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

class OnboardingPacketCreate(BaseModel):
    employee_id: UUID
    requested_items: Dict[str, Any] = Field(default_factory=lambda: {"i9": True, "w4": True, "ssn": True, "direct_deposit": True})

class OnboardingPacketPatch(BaseModel):
    status: Optional[str] = None
    submitted_items: Optional[Dict[str, Any]] = None

class CaseOut(BaseModel):
    id: UUID
    org_id: UUID
    reporter_employee_id: Optional[UUID] = None
    is_anonymous: bool
    category: str
    severity: str
    details: str
    status: str
    escalation_level: int
    created_at: datetime

class CaseCreate(BaseModel):
    category: str
    severity: str = "medium"
    details: str
    is_anonymous: bool = True
    reporter_employee_id: Optional[UUID] = None

class JobOut(BaseModel):
    id: UUID
    org_id: UUID
    title: str
    location: Optional[str] = None
    description: str
    status: str
    created_at: datetime

class JobCreate(BaseModel):
    title: str
    location: Optional[str] = None
    description: str
    status: str = "draft"

class CandidateOut(BaseModel):
    id: UUID
    org_id: UUID
    job_posting_id: UUID
    full_name: str
    email: str
    resume_text: Optional[str] = None
    status: str
    ai_score: Optional[int] = None
    ai_summary: Optional[str] = None
    created_at: datetime

class CandidateCreate(BaseModel):
    job_posting_id: UUID
    full_name: str
    email: str
    resume_text: Optional[str] = None
