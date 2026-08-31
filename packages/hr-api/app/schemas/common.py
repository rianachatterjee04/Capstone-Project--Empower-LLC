from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime

class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class AuditEvent(BaseModel):
    action: str
    entity_type: str
    entity_id: str
    meta: dict = {}
