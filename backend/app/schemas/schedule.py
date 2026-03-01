import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.schedule import ScheduleStatus


class ScheduleCreate(BaseModel):
    name: str | None = None
    period_start: date
    period_end: date


class ScheduleUpdate(BaseModel):
    name: str | None = None
    status: ScheduleStatus | None = None
    user_rating: int | None = None
    user_feedback_text: str | None = None


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str | None
    period_start: date
    period_end: date
    status: str
    generated_by_agent: bool
    agent_version: str | None
    agent_confidence: float | None
    user_rating: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
