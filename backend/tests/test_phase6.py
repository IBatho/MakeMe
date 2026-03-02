"""
Phase 6 tests:
  - Apple CalDAV iCal mapper (no network required)
  - Microsoft 365 Graph API mapper (no network required)
  - Provider registration in the registry
  - Pagination for GET /tasks and GET /events
  - CalDAV connect endpoint
"""

from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def encryption_key(monkeypatch):
    """Provide a valid Fernet key for tests that call encrypt_token."""
    import app.core.encryption as enc

    key = Fernet.generate_key().decode()
    monkeypatch.setattr("app.core.config.settings.ENCRYPTION_KEY", key)
    enc._fernet = None  # reset cached singleton so next call uses new key
    yield
    enc._fernet = None  # clean up after test

# ─────────────────────────────────────────────────────────────────────────────
# CalDAV mapper tests
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_ICAL = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-uid-abc123
SUMMARY:Team standup
DTSTART:20240315T090000Z
DTEND:20240315T093000Z
DESCRIPTION:Daily sync
LOCATION:Office 4B
END:VEVENT
END:VCALENDAR
"""

SAMPLE_ICAL_ALLDAY = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:allday-uid-456
SUMMARY:Public Holiday
DTSTART;VALUE=DATE:20240325
DTEND;VALUE=DATE:20240326
END:VEVENT
END:VCALENDAR
"""


def test_parse_ical_events_returns_uid_vevent_pairs():
    from app.integrations.apple_caldav.mapper import parse_ical_events

    results = parse_ical_events(SAMPLE_ICAL)
    assert len(results) == 1
    uid, vevent = results[0]
    assert uid == "test-uid-abc123"
    assert str(vevent.get("SUMMARY")) == "Team standup"


def test_vevent_to_normalised_basic():
    from app.integrations.apple_caldav.mapper import parse_ical_events, vevent_to_normalised

    uid, vevent = parse_ical_events(SAMPLE_ICAL)[0]
    event = vevent_to_normalised(vevent, source_id=uid)

    assert event.source_id == "test-uid-abc123"
    assert event.title == "Team standup"
    assert event.description == "Daily sync"
    assert event.location == "Office 4B"
    assert event.is_all_day is False
    assert event.start_time.tzinfo is not None
    assert event.start_time.year == 2024
    assert event.start_time.month == 3
    assert event.start_time.day == 15


def test_vevent_to_normalised_all_day():
    from app.integrations.apple_caldav.mapper import parse_ical_events, vevent_to_normalised

    uid, vevent = parse_ical_events(SAMPLE_ICAL_ALLDAY)[0]
    event = vevent_to_normalised(vevent, source_id=uid)

    assert event.is_all_day is True
    assert event.title == "Public Holiday"


def test_normalised_to_ical_roundtrip():
    from app.integrations.apple_caldav.mapper import (
        normalised_to_ical,
        parse_ical_events,
        vevent_to_normalised,
    )
    from app.integrations.base import NormalisedEvent

    original = NormalisedEvent(
        source_id="round-trip-uid",
        title="Round-trip event",
        start_time=datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 6, 1, 11, 0, tzinfo=timezone.utc),
        description="This is a test",
        location="Somewhere",
    )

    ical_bytes = normalised_to_ical(original, uid="round-trip-uid")
    assert isinstance(ical_bytes, bytes)

    pairs = parse_ical_events(ical_bytes)
    assert len(pairs) == 1
    uid, vevent = pairs[0]
    assert uid == "round-trip-uid"

    recovered = vevent_to_normalised(vevent, source_id=uid)
    assert recovered.title == "Round-trip event"
    assert recovered.start_time.year == 2024
    assert recovered.start_time.hour == 10


# ─────────────────────────────────────────────────────────────────────────────
# Microsoft 365 mapper tests
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_GRAPH_EVENT = {
    "id": "graph-event-id-789",
    "subject": "Project review",
    "bodyPreview": "Q2 planning session",
    "start": {"dateTime": "2024-04-10T14:00:00", "timeZone": "UTC"},
    "end": {"dateTime": "2024-04-10T15:30:00", "timeZone": "UTC"},
    "location": {"displayName": "Meeting Room 2"},
    "isAllDay": False,
    "webLink": "https://outlook.office.com/...",
}


def test_graph_event_to_normalised():
    from app.integrations.microsoft_365.mapper import graph_event_to_normalised

    event = graph_event_to_normalised(SAMPLE_GRAPH_EVENT)

    assert event.source_id == "graph-event-id-789"
    assert event.title == "Project review"
    assert event.description == "Q2 planning session"
    assert event.location == "Meeting Room 2"
    assert event.is_all_day is False
    assert event.start_time.year == 2024
    assert event.start_time.month == 4
    assert event.start_time.day == 10
    assert event.start_time.hour == 14
    assert event.metadata["graph_id"] == "graph-event-id-789"


def test_graph_event_all_day():
    from app.integrations.microsoft_365.mapper import graph_event_to_normalised

    item = {
        "id": "allday-id",
        "subject": "Bank Holiday",
        "start": {"dateTime": "2024-05-06T00:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-05-07T00:00:00", "timeZone": "UTC"},
        "isAllDay": True,
    }
    event = graph_event_to_normalised(item)
    assert event.is_all_day is True


def test_normalised_to_graph_event():
    from app.integrations.microsoft_365.mapper import normalised_to_graph_event
    from app.integrations.base import NormalisedEvent

    event = NormalisedEvent(
        source_id="ms-test",
        title="Budget meeting",
        start_time=datetime(2024, 7, 15, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 7, 15, 10, 0, tzinfo=timezone.utc),
        description="Annual review",
        location="Board room",
    )

    body = normalised_to_graph_event(event)

    assert body["subject"] == "Budget meeting"
    assert body["start"]["dateTime"] == "2024-07-15T09:00:00"
    assert body["start"]["timeZone"] == "UTC"
    assert body["end"]["dateTime"] == "2024-07-15T10:00:00"
    assert body["body"]["content"] == "Annual review"
    assert body["location"]["displayName"] == "Board room"
    assert body["isAllDay"] is False


def test_graph_missing_fields_handled():
    from app.integrations.microsoft_365.mapper import graph_event_to_normalised

    # Minimal item — should not raise
    event = graph_event_to_normalised({})
    assert event.title == "Untitled"
    assert event.start_time is not None


# ─────────────────────────────────────────────────────────────────────────────
# Provider registry tests
# ─────────────────────────────────────────────────────────────────────────────


def test_all_providers_registered():
    """Importing integrations triggers @register decorators for all providers."""
    import app.integrations  # noqa: F401 — triggers all @register decorators

    from app.integrations.registry import list_providers

    providers = list_providers()
    assert "notion" in providers
    assert "google_calendar" in providers
    assert "apple_caldav" in providers
    assert "microsoft_365" in providers


def test_get_provider_class_apple_caldav():
    from app.integrations.registry import get_provider_class
    from app.integrations.apple_caldav.provider import AppleCalDAVProvider

    cls = get_provider_class("apple_caldav")
    assert cls is AppleCalDAVProvider


def test_get_provider_class_microsoft_365():
    from app.integrations.registry import get_provider_class
    from app.integrations.microsoft_365.provider import Microsoft365Provider

    cls = get_provider_class("microsoft_365")
    assert cls is Microsoft365Provider


def test_unknown_provider_raises():
    from app.integrations.registry import get_provider_class

    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider_class("nonexistent_provider")


# ─────────────────────────────────────────────────────────────────────────────
# Pagination — GET /api/v1/tasks
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tasks_pagination_limit(client, auth_headers):
    # Create 5 tasks
    for i in range(5):
        await client.post(
            "/api/v1/tasks",
            json={"title": f"Task {i}", "total_duration_minutes": 30},
            headers=auth_headers,
        )

    resp = await client.get("/api/v1/tasks?limit=2&offset=0", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 2


@pytest.mark.asyncio
async def test_tasks_pagination_offset(client, auth_headers):
    resp_all = await client.get("/api/v1/tasks?limit=500&offset=0", headers=auth_headers)
    assert resp_all.status_code == 200
    all_tasks = resp_all.json()

    if len(all_tasks) < 2:
        pytest.skip("Not enough tasks to test offset")

    resp_offset = await client.get("/api/v1/tasks?limit=500&offset=1", headers=auth_headers)
    assert resp_offset.status_code == 200
    offset_tasks = resp_offset.json()

    assert len(offset_tasks) == len(all_tasks) - 1
    assert offset_tasks[0]["id"] == all_tasks[1]["id"]


@pytest.mark.asyncio
async def test_tasks_pagination_invalid_limit(client, auth_headers):
    resp = await client.get("/api/v1/tasks?limit=0", headers=auth_headers)
    assert resp.status_code == 422  # validation error


@pytest.mark.asyncio
async def test_tasks_pagination_limit_too_large(client, auth_headers):
    resp = await client.get("/api/v1/tasks?limit=501", headers=auth_headers)
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Pagination — GET /api/v1/events
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_pagination_limit(client, auth_headers):
    for i in range(3):
        await client.post(
            "/api/v1/events",
            json={
                "title": f"Event {i}",
                "start_time": f"2024-08-0{i+1}T10:00:00Z",
                "end_time": f"2024-08-0{i+1}T11:00:00Z",
            },
            headers=auth_headers,
        )

    resp = await client.get("/api/v1/events?limit=2", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


@pytest.mark.asyncio
async def test_events_pagination_invalid(client, auth_headers):
    resp = await client.get("/api/v1/events?limit=1001", headers=auth_headers)
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# CalDAV connect endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_caldav_connect_creates_integration(client, auth_headers, encryption_key):
    resp = await client.post(
        "/api/v1/integrations/caldav/connect",
        json={
            "username": "user@icloud.com",
            "password": "app-specific-password",
            "caldav_url": "https://caldav.icloud.com",
            "display_name": "My iCloud Calendar",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "apple_caldav"
    assert data["provider_type"] == "calendar"
    assert data["display_name"] == "My iCloud Calendar"
    assert data["is_enabled"] is True
    # Raw password must not appear in the response
    assert "app-specific-password" not in str(data)


@pytest.mark.asyncio
async def test_caldav_connect_upserts(client, auth_headers, encryption_key):
    """Second connect call updates the existing config instead of duplicating."""
    payload = {
        "username": "user2@icloud.com",
        "password": "pass1",
        "caldav_url": "https://caldav.icloud.com",
    }
    r1 = await client.post(
        "/api/v1/integrations/caldav/connect", json=payload, headers=auth_headers
    )
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    payload["password"] = "pass2"
    r2 = await client.post(
        "/api/v1/integrations/caldav/connect", json=payload, headers=auth_headers
    )
    assert r2.status_code == 201
    id2 = r2.json()["id"]

    assert id1 == id2  # same record updated, not a new one


@pytest.mark.asyncio
async def test_caldav_connect_requires_auth(client):
    resp = await client.post(
        "/api/v1/integrations/caldav/connect",
        json={"username": "u", "password": "p"},
    )
    assert resp.status_code == 401
