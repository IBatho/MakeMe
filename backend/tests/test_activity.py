"""
Tests for the activity tracking and location APIs.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


# ── helpers ───────────────────────────────────────────────────────────────────


async def _create_event(client: AsyncClient, headers: dict) -> dict:
    now = datetime.now(timezone.utc)
    resp = await client.post(
        "/api/v1/events",
        headers=headers,
        json={
            "title": "Study session",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_task_and_event(client: AsyncClient, headers: dict) -> tuple[dict, dict]:
    """Create a task and an event linked to it."""
    task_resp = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Read textbook", "priority": "want", "total_duration_minutes": 90},
    )
    task = task_resp.json()

    now = datetime.now(timezone.utc)
    event_resp = await client.post(
        "/api/v1/events",
        headers=headers,
        json={
            "title": "Read textbook",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
            "task_id": task["id"],
        },
    )
    return task, event_resp.json()


# ── activity/start ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_activity_creates_log(client: AsyncClient, auth_headers: dict):
    event = await _create_event(client, auth_headers)

    resp = await client.post(
        "/api/v1/activity/start",
        headers=auth_headers,
        json={"event_id": event["id"], "device_id": "phone-1"},
    )
    assert resp.status_code == 201
    log = resp.json()
    assert log["action"] == "started"
    assert log["event_id"] == event["id"]
    assert log["device_id"] == "phone-1"


@pytest.mark.asyncio
async def test_start_activity_sets_event_in_progress(client: AsyncClient, auth_headers: dict):
    event = await _create_event(client, auth_headers)
    await client.post(
        "/api/v1/activity/start",
        headers=auth_headers,
        json={"event_id": event["id"]},
    )

    event_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    updated = event_resp.json()
    assert updated["status"] == "in_progress"
    assert updated["actual_start_time"] is not None


# ── activity/stop ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_activity_partial_completion(client: AsyncClient, auth_headers: dict):
    event = await _create_event(client, auth_headers)
    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": event["id"]})

    resp = await client.post(
        "/api/v1/activity/stop",
        headers=auth_headers,
        json={"event_id": event["id"], "completion_percentage": 0.6, "notes": "Got interrupted"},
    )
    assert resp.status_code == 201
    log = resp.json()
    assert log["action"] == "stopped"
    assert log["completion_percentage"] == pytest.approx(0.6)

    event_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    ev = event_resp.json()
    assert ev["status"] == "cancelled"  # not fully complete
    assert ev["completion_percentage"] == pytest.approx(0.6)
    assert ev["actual_end_time"] is not None


@pytest.mark.asyncio
async def test_stop_activity_full_completion(client: AsyncClient, auth_headers: dict):
    event = await _create_event(client, auth_headers)
    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": event["id"]})

    resp = await client.post(
        "/api/v1/activity/stop",
        headers=auth_headers,
        json={"event_id": event["id"], "completion_percentage": 1.0},
    )
    log = resp.json()
    assert log["action"] == "completed"

    event_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    assert event_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_stop_activity_marks_linked_task_complete(client: AsyncClient, auth_headers: dict):
    task, event = await _create_task_and_event(client, auth_headers)

    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": event["id"]})
    await client.post(
        "/api/v1/activity/stop",
        headers=auth_headers,
        json={"event_id": event["id"], "completion_percentage": 1.0},
    )

    task_resp = await client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers)
    assert task_resp.json()["is_complete"] is True


# ── activity/update ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_activity_mid_session(client: AsyncClient, auth_headers: dict):
    event = await _create_event(client, auth_headers)
    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": event["id"]})

    resp = await client.post(
        "/api/v1/activity/update",
        headers=auth_headers,
        json={"event_id": event["id"], "completion_percentage": 0.4},
    )
    assert resp.status_code == 201
    assert resp.json()["action"] == "paused"

    event_resp = await client.get(f"/api/v1/events/{event['id']}", headers=auth_headers)
    assert event_resp.json()["completion_percentage"] == pytest.approx(0.4)


# ── GET /activity ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_activity_logs(client: AsyncClient, auth_headers: dict):
    event = await _create_event(client, auth_headers)

    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": event["id"]})
    await client.post(
        "/api/v1/activity/stop",
        headers=auth_headers,
        json={"event_id": event["id"], "completion_percentage": 1.0},
    )

    resp = await client.get("/api/v1/activity", headers=auth_headers)
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) >= 2
    actions = {l["action"] for l in logs}
    assert "started" in actions
    assert "completed" in actions


@pytest.mark.asyncio
async def test_list_activity_filter_by_event(client: AsyncClient, auth_headers: dict):
    e1 = await _create_event(client, auth_headers)
    e2 = await _create_event(client, auth_headers)

    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": e1["id"]})
    await client.post("/api/v1/activity/start", headers=auth_headers, json={"event_id": e2["id"]})

    resp = await client.get(f"/api/v1/activity?event_id={e1['id']}", headers=auth_headers)
    logs = resp.json()
    assert all(l["event_id"] == e1["id"] for l in logs)


@pytest.mark.asyncio
async def test_activity_event_not_found(client: AsyncClient, auth_headers: dict):
    import uuid

    resp = await client.post(
        "/api/v1/activity/start",
        headers=auth_headers,
        json={"event_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
