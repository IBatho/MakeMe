"""
Tests for the integration API and sync service.

Provider API calls (Notion DB query, Google OAuth token exchange) are mocked
so tests run fully offline without any external credentials.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient

from app.integrations.base import NormalisedTask, NormalisedEvent, TokenData
from app.integrations.notion.mapper import notion_page_to_task
from app.integrations.google_calendar.mapper import gcal_event_to_normalised

# ── Test encryption key ────────────────────────────────────────────────────────
# Fernet requires a URL-safe base64-encoded 32-byte key.
_TEST_FERNET_KEY = Fernet.generate_key().decode()


# Override the encryption key so Fernet operations work in tests
@pytest.fixture(autouse=True)
def patch_encryption_key(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.ENCRYPTION_KEY", _TEST_FERNET_KEY)
    # Reset the cached Fernet instance so it picks up the new key
    import app.core.encryption as enc_module
    enc_module._fernet = None
    yield
    enc_module._fernet = None


# ── Notion mapper unit tests ───────────────────────────────────────────────────


def _make_notion_page(
    page_id: str = "abc-123",
    name: str = "Write report",
    priority: str = "Want",
    duration: int = 90,
    deadline: str | None = "2026-04-01",
    done: bool = False,
) -> dict:
    props: dict = {
        "Name": {"title": [{"plain_text": name}]},
        "Priority": {"select": {"name": priority}},
        "Duration": {"number": duration},
        "Done": {"checkbox": done},
    }
    if deadline:
        props["Deadline"] = {"date": {"start": deadline}}
    return {"id": page_id, "url": f"https://notion.so/{page_id}", "properties": props}


def test_notion_mapper_basic():
    page = _make_notion_page()
    task = notion_page_to_task(page)

    assert task.source_id == "abc-123"
    assert task.title == "Write report"
    assert task.priority == "want"
    assert task.total_duration_minutes == 90
    assert task.deadline == date(2026, 4, 1)
    assert task.is_complete is False


def test_notion_mapper_priority_mapping():
    assert notion_page_to_task(_make_notion_page(priority="Need")).priority == "need"
    assert notion_page_to_task(_make_notion_page(priority="Like")).priority == "like"
    assert notion_page_to_task(_make_notion_page(priority="High")).priority == "need"
    assert notion_page_to_task(_make_notion_page(priority="Low")).priority == "like"


def test_notion_mapper_done_checkbox():
    task = notion_page_to_task(_make_notion_page(done=True))
    assert task.is_complete is True


def test_notion_mapper_missing_duration_defaults_to_60():
    page = _make_notion_page()
    page["properties"]["Duration"] = {"number": None}
    task = notion_page_to_task(page)
    assert task.total_duration_minutes == 60


# ── Google Calendar mapper unit tests ─────────────────────────────────────────


def _make_gcal_event(
    event_id: str = "gcal-1",
    summary: str = "Team standup",
    start: str = "2026-04-01T09:00:00+00:00",
    end: str = "2026-04-01T09:30:00+00:00",
    all_day: bool = False,
) -> dict:
    if all_day:
        return {
            "id": event_id,
            "summary": summary,
            "start": {"date": start[:10]},
            "end": {"date": end[:10]},
        }
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }


def test_gcal_mapper_timed_event():
    gcal = _make_gcal_event()
    event = gcal_event_to_normalised(gcal)

    assert event.source_id == "gcal-1"
    assert event.title == "Team standup"
    assert event.is_all_day is False
    assert event.start_time == datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)


def test_gcal_mapper_all_day():
    gcal = _make_gcal_event(all_day=True, start="2026-04-01", end="2026-04-02")
    event = gcal_event_to_normalised(gcal)
    assert event.is_all_day is True


# ── Integration API tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_integrations_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/integrations", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_integration_token_auth(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={
            "provider": "notion",
            "api_token": "secret_test_token_abc",
            "display_name": "My Notion",
            "config": {"database_id": "db-123"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "notion"
    assert data["provider_type"] == "task_source"
    assert data["display_name"] == "My Notion"
    assert data["is_enabled"] is True
    assert "id" in data
    return data


@pytest.mark.asyncio
async def test_get_integration(client: AsyncClient, auth_headers: dict):
    # Create
    create_resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "notion", "api_token": "tok", "config": {"database_id": "db-x"}},
    )
    integration_id = create_resp.json()["id"]

    # Get
    resp = await client.get(f"/api/v1/integrations/{integration_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == integration_id


@pytest.mark.asyncio
async def test_update_integration(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "notion", "api_token": "tok2", "config": {"database_id": "db-y"}},
    )
    integration_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/integrations/{integration_id}",
        headers=auth_headers,
        json={"display_name": "Updated Name", "is_enabled": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Updated Name"
    assert data["is_enabled"] is False


@pytest.mark.asyncio
async def test_delete_integration(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "notion", "api_token": "tok3", "config": {"database_id": "db-z"}},
    )
    integration_id = create_resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/integrations/{integration_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/integrations/{integration_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_integration_unknown_provider(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "nonexistent_provider", "api_token": "tok"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_integration_no_token_returns_400(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "notion"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_oauth_url_notion(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/integrations/oauth/notion/url", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "api.notion.com" in data["url"]
    assert "state" in data


@pytest.mark.asyncio
async def test_oauth_url_google_calendar(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/integrations/oauth/google_calendar/url", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "accounts.google.com" in data["url"]


@pytest.mark.asyncio
async def test_oauth_url_unknown_provider(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/v1/integrations/oauth/unknown_provider/url", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sync_integration_with_mocked_provider(client: AsyncClient, auth_headers: dict):
    """POST /integrations/{id}/sync should call fetch_tasks() and upsert into DB."""
    # Create integration
    create_resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "notion", "api_token": "test_tok", "config": {"database_id": "db-sync"}},
    )
    assert create_resp.status_code == 201
    integration_id = create_resp.json()["id"]

    # Mock NotionProvider.fetch_tasks to return two tasks
    mock_tasks = [
        NormalisedTask(
            source_id="nt-1",
            title="Buy groceries",
            priority="like",
            total_duration_minutes=30,
        ),
        NormalisedTask(
            source_id="nt-2",
            title="Finish essay",
            priority="need",
            total_duration_minutes=120,
            deadline=date(2026, 4, 10),
        ),
    ]

    with patch(
        "app.integrations.notion.provider.NotionProvider.fetch_tasks",
        new_callable=AsyncMock,
        return_value=mock_tasks,
    ):
        sync_resp = await client.post(
            f"/api/v1/integrations/{integration_id}/sync", headers=auth_headers
        )

    assert sync_resp.status_code == 200
    result = sync_resp.json()
    assert result["tasks_upserted"] == 2
    assert result["events_upserted"] == 0
    assert result["errors"] == []

    # Re-sync — tasks should be updated (not duplicated)
    with patch(
        "app.integrations.notion.provider.NotionProvider.fetch_tasks",
        new_callable=AsyncMock,
        return_value=mock_tasks,
    ):
        sync_resp2 = await client.post(
            f"/api/v1/integrations/{integration_id}/sync", headers=auth_headers
        )

    result2 = sync_resp2.json()
    assert result2["tasks_upserted"] == 2  # updated, not duplicated

    # Verify tasks appear in task list
    tasks_resp = await client.get("/api/v1/tasks", headers=auth_headers)
    titles = [t["title"] for t in tasks_resp.json()]
    assert "Buy groceries" in titles
    assert "Finish essay" in titles


@pytest.mark.asyncio
async def test_sync_disabled_integration_returns_400(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/integrations",
        headers=auth_headers,
        json={"provider": "notion", "api_token": "tok4", "config": {"database_id": "db-off"}},
    )
    integration_id = create_resp.json()["id"]

    await client.patch(
        f"/api/v1/integrations/{integration_id}",
        headers=auth_headers,
        json={"is_enabled": False},
    )

    sync_resp = await client.post(
        f"/api/v1/integrations/{integration_id}/sync", headers=auth_headers
    )
    assert sync_resp.status_code == 400


@pytest.mark.asyncio
async def test_integration_not_found_returns_404(client: AsyncClient, auth_headers: dict):
    import uuid

    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/integrations/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404
