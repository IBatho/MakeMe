import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from app.models.event import EventStatus


class EventCreate(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    start_time: datetime
    end_time: datetime
    is_all_day: bool = False
    task_id: uuid.UUID | None = None
    schedule_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> "EventCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    is_locked: bool | None = None
    status: EventStatus | None = None
    completion_percentage: float | None = None


class EventResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    task_id: uuid.UUID | None
    schedule_id: uuid.UUID | None
    title: str
    description: str | None
    location: str | None
    start_time: datetime
    end_time: datetime
    is_all_day: bool
    status: str
    is_agent_created: bool
    is_locked: bool
    completion_percentage: float
    provider: str | None
    provider_event_id: str | None
    actual_start_time: datetime | None
    actual_end_time: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
