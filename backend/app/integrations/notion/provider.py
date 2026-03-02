"""
Notion integration provider.

Supports two auth modes (set via config["auth_type"]):
  "oauth"  – OAuth 2 integration token (default for new connections)
  "token"  – internal Notion integration secret (set via credentials_encrypted)

fetch_tasks() pages through a Notion database and returns NormalisedTask objects.
"""

import urllib.parse
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.base import (
    IntegrationProvider,
    NormalisedTask,
    ProviderContext,
    TokenData,
)
from app.integrations.notion.mapper import notion_page_to_task
from app.integrations.registry import register

_NOTION_API = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


@register("notion")
class NotionProvider(IntegrationProvider):
    """Fetches tasks from a Notion database."""

    def __init__(self, context: ProviderContext) -> None:
        super().__init__(context)
        self._token = context.access_token  # works for both OAuth + internal token

    @property
    def provider_name(self) -> str:
        return "notion"

    @property
    def provider_type(self) -> str:
        return "task_source"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def fetch_tasks(self) -> list[NormalisedTask]:
        database_id = self.ctx.extra_config.get("database_id")
        if not database_id:
            raise ValueError("Notion provider requires 'database_id' in config")

        tasks: list[NormalisedTask] = []
        start_cursor: str | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                body: dict[str, Any] = {}
                if start_cursor:
                    body["start_cursor"] = start_cursor

                resp = await client.post(
                    f"{_NOTION_API}/databases/{database_id}/query",
                    headers=self._headers(),
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()

                for page in data.get("results", []):
                    tasks.append(notion_page_to_task(page))

                if not data.get("has_more"):
                    break
                start_cursor = data.get("next_cursor")

        return tasks

    # ── OAuth ────────────────────────────────────────────────────────────────

    @classmethod
    def get_oauth_url(cls, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": settings.NOTION_CLIENT_ID,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"https://api.notion.com/v1/oauth/authorize?{urllib.parse.urlencode(params)}"

    @classmethod
    async def exchange_code(cls, code: str, redirect_uri: str) -> TokenData:
        import base64

        creds = base64.b64encode(
            f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.notion.com/v1/oauth/token",
                headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        # Notion tokens don't expire; no refresh token issued
        return TokenData(
            access_token=data["access_token"],
            extra={
                "workspace_id": data.get("workspace_id"),
                "workspace_name": data.get("workspace_name"),
                "bot_id": data.get("bot_id"),
            },
        )
