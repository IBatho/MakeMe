"""
Microsoft 365 Calendar integration provider.

Uses the Microsoft Graph API v1.0 to read and write calendar events.
OAuth 2.0 via Azure AD (common endpoint) with scopes: Calendars.ReadWrite offline_access.
"""

from __future__ import annotations

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
from app.integrations.microsoft_365.mapper import (
    graph_event_to_normalised,
    normalised_to_graph_event,
)
from app.integrations.registry import register

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_SCOPES = "Calendars.ReadWrite offline_access"


@register("microsoft_365")
class Microsoft365Provider(IntegrationProvider):
    """Reads and writes Microsoft 365 Calendar events via the Graph API."""

    def __init__(self, context: ProviderContext) -> None:
        super().__init__(context)
        # Optional: specify a specific calendar ID (defaults to primary)
        self._calendar_id: str = context.extra_config.get("calendar_id", "")

    @property
    def provider_name(self) -> str:
        return "microsoft_365"

    @property
    def provider_type(self) -> str:
        return "calendar"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.ctx.access_token}",
            "Content-Type": "application/json",
        }

    def _events_url(self) -> str:
        if self._calendar_id:
            return f"{_GRAPH_BASE}/me/calendars/{self._calendar_id}/events"
        return f"{_GRAPH_BASE}/me/events"

    async def fetch_events(self, start: datetime, end: datetime) -> list[NormalisedEvent]:
        start_str = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        end_str = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        initial_params: dict = {
            "$filter": f"start/dateTime ge '{start_str}' and end/dateTime le '{end_str}'",
            "$select": "id,subject,bodyPreview,start,end,location,isAllDay,webLink",
            "$top": "100",
            "$orderby": "start/dateTime",
        }

        events: list[NormalisedEvent] = []
        url: str | None = self._events_url()
        params: dict | None = initial_params

        async with httpx.AsyncClient(timeout=30.0) as client:
            while url:
                resp = await client.get(url, headers=self._headers(), params=params)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("value", []):
                    events.append(graph_event_to_normalised(item))

                # @odata.nextLink already encodes all query params
                url = data.get("@odata.nextLink")
                params = None

        return events

    async def create_event(self, event: NormalisedEvent) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self._events_url(),
                headers=self._headers(),
                json=normalised_to_graph_event(event),
            )
            resp.raise_for_status()
        return resp.json()["id"]

    async def update_event(self, provider_event_id: str, event: NormalisedEvent) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(
                f"{_GRAPH_BASE}/me/events/{provider_event_id}",
                headers=self._headers(),
                json=normalised_to_graph_event(event),
            )
            resp.raise_for_status()

    async def delete_event(self, provider_event_id: str) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{_GRAPH_BASE}/me/events/{provider_event_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def refresh_access_token(self) -> TokenData:
        if not self.ctx.refresh_token:
            raise ValueError("No refresh token — re-authorise Microsoft 365")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.ctx.refresh_token,
                    "client_id": settings.MICROSOFT_CLIENT_ID,
                    "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                    "scope": _SCOPES,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_at = None
        if "expires_in" in data:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))

        return TokenData(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", self.ctx.refresh_token),
            expires_at=expires_at,
            scope=data.get("scope"),
        )

    # ── OAuth ─────────────────────────────────────────────────────────────────

    @classmethod
    def get_oauth_url(cls, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": _SCOPES,
            "response_mode": "query",
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
                    "client_id": settings.MICROSOFT_CLIENT_ID,
                    "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                    "scope": _SCOPES,
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
