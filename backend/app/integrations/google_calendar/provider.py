"""
Google Calendar integration provider.

Reads and writes events using the Google Calendar REST API v3.
OAuth 2 with offline access (access + refresh tokens).
"""

import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.integrations.base import (
    IntegrationProvider,
    NormalisedEvent,
    ProviderContext,
    TokenData,
)
from app.integrations.google_calendar.mapper import gcal_event_to_normalised, normalised_to_gcal_event
from app.integrations.registry import register

_GCAL_BASE = "https://www.googleapis.com/calendar/v3"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPES = "https://www.googleapis.com/auth/calendar"


@register("google_calendar")
class GoogleCalendarProvider(IntegrationProvider):
    """Reads and writes events on a user's Google Calendar."""

    def __init__(self, context: ProviderContext) -> None:
        super().__init__(context)
        self._calendar_id = context.extra_config.get("calendar_id", "primary")

    @property
    def provider_name(self) -> str:
        return "google_calendar"

    @property
    def provider_type(self) -> str:
        return "calendar"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.ctx.access_token}"}

    async def fetch_events(self, start: datetime, end: datetime) -> list[NormalisedEvent]:
        params: dict = {
            "timeMin": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "timeMax": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        }
        events: list[NormalisedEvent] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                resp = await client.get(
                    f"{_GCAL_BASE}/calendars/{self._calendar_id}/events",
                    headers=self._headers(),
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("items", []):
                    if item.get("status") != "cancelled":
                        events.append(gcal_event_to_normalised(item))

                page_token = data.get("nextPageToken")
                if not page_token:
                    break
                params["pageToken"] = page_token

        return events

    async def create_event(self, event: NormalisedEvent) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_GCAL_BASE}/calendars/{self._calendar_id}/events",
                headers=self._headers(),
                json=normalised_to_gcal_event(event),
            )
            resp.raise_for_status()
        return resp.json()["id"]

    async def update_event(self, provider_event_id: str, event: NormalisedEvent) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                f"{_GCAL_BASE}/calendars/{self._calendar_id}/events/{provider_event_id}",
                headers=self._headers(),
                json=normalised_to_gcal_event(event),
            )
            resp.raise_for_status()

    async def delete_event(self, provider_event_id: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{_GCAL_BASE}/calendars/{self._calendar_id}/events/{provider_event_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def refresh_access_token(self) -> TokenData:
        if not self.ctx.refresh_token:
            raise ValueError("No refresh token — re-authorise Google Calendar")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.ctx.refresh_token,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_at = None
        if "expires_in" in data:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))

        return TokenData(
            access_token=data["access_token"],
            refresh_token=self.ctx.refresh_token,  # Google reuses the same refresh token
            expires_at=expires_at,
            scope=data.get("scope"),
        )

    # ── OAuth ────────────────────────────────────────────────────────────────

    @classmethod
    def get_oauth_url(cls, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"

    @classmethod
    async def exchange_code(cls, code: str, redirect_uri: str) -> TokenData:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_at = None
        if "expires_in" in data:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))

        return TokenData(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            scope=data.get("scope"),
        )
