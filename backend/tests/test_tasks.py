import pytest
from httpx import AsyncClient


TASK_PAYLOAD = {
    "title": "Study for exam",
    "priority": "want",
    "total_duration_minutes": 120,
    "min_block_minutes": 30,
    "max_block_minutes": 90,
}


async def test_create_task(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Study for exam"
    assert data["priority"] == "want"
    assert data["is_complete"] is False
    return data["id"]


async def test_list_tasks(client: AsyncClient, auth_headers: dict):
    await client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    resp = await client.get("/api/v1/tasks", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


async def test_list_tasks_filter_priority(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/tasks",
        json={**TASK_PAYLOAD, "title": "Must-do task", "priority": "need"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/tasks?priority=need", headers=auth_headers)
    assert resp.status_code == 200
    for task in resp.json():
        assert task["priority"] == "need"


async def test_get_task(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    task_id = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id


async def test_update_task(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    task_id = create_resp.json()["id"]
    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated title", "completion_percentage": 0.5},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated title"
    assert resp.json()["completion_percentage"] == 0.5


async def test_complete_task(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    task_id = create_resp.json()["id"]
    resp = await client.post(f"/api/v1/tasks/{task_id}/complete", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_complete"] is True
    assert resp.json()["completion_percentage"] == 1.0


async def test_delete_task(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post("/api/v1/tasks", json=TASK_PAYLOAD, headers=auth_headers)
    task_id = create_resp.json()["id"]
    del_resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert del_resp.status_code == 204
    get_resp = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert get_resp.status_code == 404


async def test_task_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/tasks")
    assert resp.status_code == 403
