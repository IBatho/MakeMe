import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class ActivityStart(BaseModel):
    event_id: uuid.UUID
    device_id: str | None = None


class ActivityStop(BaseModel):
    event_id: uuid.UUID
    completion_percentage: float = 1.0
    notes: str | None = None
    device_id: str | None = None

    @field_validator("completion_percentage")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class ActivityUpdate(BaseModel):
    event_id: uuid.UUID
    completion_percentage: float
    notes: str | None = None
    device_id: str | None = None

    @field_validator("completion_percentage")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class ActivityResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID | None
    task_id: uuid.UUID | None
    logged_at: datetime
    action: str
    completion_percentage: float | None
    notes: str | None
    device_id: str | None
    source: str

    model_config = {"from_attributes": True}
