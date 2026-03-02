import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class LocationPingCreate(BaseModel):
    latitude: float
    longitude: float
    accuracy_meters: float | None = None
    event_id: uuid.UUID | None = None
    context: str | None = None  # "pre_event" | "post_event" | "free"

    @field_validator("latitude")
    @classmethod
    def valid_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def valid_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return v


class LocationPingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    pinged_at: datetime
    latitude: float
    longitude: float
    accuracy_meters: float | None
    event_id: uuid.UUID | None
    context: str | None

    model_config = {"from_attributes": True}


class TravelTimeResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    origin_label: str
    destination_label: str
    origin_lat: float
    origin_lon: float
    destination_lat: float
    destination_lon: float
    sample_count: int
    mean_duration_minutes: float | None
    std_deviation_minutes: float | None
    min_duration_minutes: float | None
    max_duration_minutes: float | None
    hourly_means: dict | None
    day_of_week_means: dict | None
    last_observed_at: datetime | None

    model_config = {"from_attributes": True}
