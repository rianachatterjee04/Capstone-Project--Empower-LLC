from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from .common import ORMBase

class PacketCreate(BaseModel):
    employee_id: UUID
    requested_items: dict  # e.g. {"i9": True, "w4": True, "ssn": True, "direct_deposit": True}

class PacketUpdate(BaseModel):
    status: str | None = None
    submitted_items: dict | None = None

class PacketOut(ORMBase):
    id: UUID
    org_id: UUID
    employee_id: UUID
    status: str
    requested_items: dict
    submitted_items: dict
    created_at: datetime
