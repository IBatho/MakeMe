import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class IntegrationCreate(BaseModel):
    """Body for POST /integrations (non-OAuth / internal-token providers like Notion)."""

    provider: str
    display_name: str | None = None
    # For providers that use an internal token instead of OAuth (e.g. Notion internal integration)
    api_token: str | None = None
    # Provider-specific config (database_id, calendar_id, etc.)
    config: dict[str, Any] | None = None


class IntegrationUpdate(BaseModel):
    is_enabled: bool | None = None
    display_name: str | None = None
    config: dict[str, Any] | None = None


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    provider: str
    provider_type: str
    is_enabled: bool
    display_name: str | None
    last_synced_at: datetime | None
    last_sync_status: str | None
    last_sync_error: str | None
    config: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OAuthUrlResponse(BaseModel):
    url: str
    state: str


class SyncResult(BaseModel):
    tasks_upserted: int = 0
    events_upserted: int = 0
    errors: list[str] = []


class CalDAVConnectBody(BaseModel):
    """Body for POST /integrations/caldav/connect — Basic Auth setup."""

    username: str
    password: str
    caldav_url: str = "https://caldav.icloud.com"
    display_name: str | None = None
