from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from .common import ORMBase

class OrgCreate(BaseModel):
    name: str

class OrgOut(ORMBase):
    id: UUID
    name: str
    created_at: datetime
