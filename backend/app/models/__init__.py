# Import all models so they are registered with Base.metadata
# This is required for Alembic autogenerate and for SQLAlchemy to create tables.
from app.models.base import Base
from app.models.user import User
from app.models.task import Task
from app.models.schedule import Schedule
from app.models.event import Event
from app.models.activity_log import ActivityLog
from app.models.location import LocationPing
from app.models.travel_time import TravelTime
from app.models.integration_config import IntegrationConfig

__all__ = [
    "Base",
    "User",
    "Task",
    "Schedule",
    "Event",
    "ActivityLog",
    "LocationPing",
    "TravelTime",
    "IntegrationConfig",
]
