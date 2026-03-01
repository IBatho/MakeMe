import uuid
from datetime import datetime

from sqlalchemy import Float, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TravelTime(Base, TimestampMixin):
    """
    Aggregated travel time estimates between a pair of locations for a user.
    Updated by the location service after each trip is detected.
    """

    __tablename__ = "travel_times"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Human-readable labels (e.g. "Home", "University Library")
    origin_label: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_label: Mapped[str] = mapped_column(String(255), nullable=False)

    # Centroid coordinates for the detected cluster
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lon: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lat: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lon: Mapped[float] = mapped_column(Float, nullable=False)

    # Aggregate stats
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mean_duration_minutes: Mapped[float | None] = mapped_column(Float)
    std_deviation_minutes: Mapped[float | None] = mapped_column(Float)
    min_duration_minutes: Mapped[float | None] = mapped_column(Float)
    max_duration_minutes: Mapped[float | None] = mapped_column(Float)

    # Time-of-day segmentation (24-item list, index = hour 0–23)
    hourly_means: Mapped[dict | None] = mapped_column(JSONB)
    # Day-of-week means (keys "0"–"6", 0=Monday)
    day_of_week_means: Mapped[dict | None] = mapped_column(JSONB)

    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
