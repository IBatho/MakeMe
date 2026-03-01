import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.models.task import TaskPriority


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: TaskPriority = TaskPriority.WANT
    total_duration_minutes: int
    min_block_minutes: int = 30
    max_block_minutes: int = 120
    deadline: date | None = None
    window_start: date | None = None
    window_end: date | None = None
    recurrence_period_days: int | None = None

    @field_validator("total_duration_minutes", "min_block_minutes", "max_block_minutes")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Duration must be positive")
        return v


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    total_duration_minutes: int | None = None
    min_block_minutes: int | None = None
    max_block_minutes: int | None = None
    deadline: date | None = None
    window_start: date | None = None
    window_end: date | None = None
    recurrence_period_days: int | None = None
    completion_percentage: float | None = None
    is_complete: bool | None = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str | None
    priority: str
    total_duration_minutes: int
    min_block_minutes: int
    max_block_minutes: int
    deadline: date | None
    window_start: date | None
    window_end: date | None
    recurrence_period_days: int | None
    completion_percentage: float
    is_complete: bool
    source: str
    source_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
