from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from uuid import UUID
from datetime import date, datetime

class PolicyCreate(BaseModel):
    name: str
    body: str

class PolicyOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    body: str
    dsl: Dict[str, Any]
    version: int
    status: str
    created_at: datetime

class EscalationRuleCreate(BaseModel):
    name: str
    entity_type: str = "case"
    condition_dsl: Dict[str, Any] = Field(default_factory=dict)
    sla_minutes: int = 48 * 60
    route: Dict[str, Any] = Field(default_factory=lambda: {"roles": ["manager","hr","legal","exec"]})
    severity_floor: Optional[str] = "high"
    is_active: bool = True

class EscalationRuleOut(EscalationRuleCreate):
    id: UUID
    org_id: UUID
    created_at: datetime

class EscalationOut(BaseModel):
    id: UUID
    org_id: UUID
    entity_type: str
    entity_id: UUID
    rule_id: UUID
    level: int
    status: str
    due_at: datetime
    last_notified_at: Optional[datetime] = None
    created_at: datetime

class MemoryUpsert(BaseModel):
    namespace: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None

class MemorySearch(BaseModel):
    namespace: str
    query: str
    k: int = 5

class MemoryOut(BaseModel):
    id: UUID
    namespace: str
    content: str
    metadata: Dict[str, Any]
