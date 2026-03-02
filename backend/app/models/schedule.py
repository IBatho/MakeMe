import uuid
from datetime import date
from enum import Enum

from sqlalchemy import String, Integer, Float, Boolean, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONBType, TimestampMixin


class ScheduleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(255))
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=ScheduleStatus.DRAFT, nullable=False)

    # Agent metadata
    generated_by_agent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(50))
    agent_confidence: Mapped[float | None] = mapped_column(Float)
    # Snapshot of context (tasks, constraints) used when the schedule was generated
    generation_context: Mapped[dict | None] = mapped_column(JSONBType)

    # User feedback (filled in after the schedule period ends)
    user_rating: Mapped[int | None] = mapped_column(Integer)
    user_feedback_text: Mapped[str | None] = mapped_column(String(2000))

    user = relationship("User", back_populates="schedules")
    events = relationship("Event", back_populates="schedule")
