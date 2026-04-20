"""Organization request/response schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class OrgRead(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    is_active: bool
    is_suspended: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgCreate(BaseModel):
    name: str
    slug: str
    timezone: str = "Asia/Kolkata"


class OrgUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None
    is_active: bool | None = None


class OrgSuspend(BaseModel):
    reason: str
