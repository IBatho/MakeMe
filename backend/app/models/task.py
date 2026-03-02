import uuid
from datetime import date
from enum import Enum

from sqlalchemy import String, Integer, Float, Boolean, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONBType, TimestampMixin


class TaskPriority(str, Enum):
    NEED = "need"   # cannot be moved
    WANT = "want"   # must happen within a window, but time block is flexible
    LIKE = "like"   # fill in when there's room


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    priority: Mapped[str] = mapped_column(String(10), default=TaskPriority.WANT, nullable=False)

    # Duration constraints
    total_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    min_block_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_block_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)

    # Scheduling window
    deadline: Mapped[date | None] = mapped_column(Date)
    window_start: Mapped[date | None] = mapped_column(Date)
    window_end: Mapped[date | None] = mapped_column(Date)

    # Recurrence (e.g. "study 2hrs per week" → total_duration_minutes=120, recurrence_period_days=7)
    recurrence_period_days: Mapped[int | None] = mapped_column(Integer)

    # Progress
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Integration source
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255))  # ID in external system

    # Extra data from integration providers
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONBType)

    user = relationship("User", back_populates="tasks")
    events = relationship("Event", back_populates="task")
