import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator

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


class RateScheduleRequest(BaseModel):
    rating: int
    feedback_text: str | None = None

    @field_validator("rating")
    @classmethod
    def rating_in_range(cls, v: int) -> int:
        if not (1 <= v <= 5):
            raise ValueError("rating must be between 1 and 5")
        return v


class GenerateScheduleRequest(BaseModel):
    period_start: date
    period_end: date

    @field_validator("period_end")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        start = info.data.get("period_start")
        if start and v < start:
            raise ValueError("period_end must be >= period_start")
        return v


class GenerateScheduleResponse(ScheduleResponse):
    """Extended response that includes a summary of what the agent placed."""

    tasks_total: int = 0
    tasks_scheduled: int = 0
    blocks_placed: int = 0
