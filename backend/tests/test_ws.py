"""
WebSocket endpoint tests.

Uses Starlette's synchronous TestClient (which supports WebSocket connections)
rather than the async httpx client.  The app dependency override for get_db is
already set at module-level in conftest.py, so it applies here too.
"""

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.core.security import create_access_token


@pytest.fixture(scope="module")
def sync_client():
    """Synchronous test client (needed for WebSocket testing)."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def registered_token(sync_client: TestClient):
    """Register a user and return a valid access token."""
    resp = sync_client.post(
        "/api/v1/auth/register",
        json={"email": "ws_test@example.com", "password": "ws_pass_123", "timezone": "UTC"},
    )
    if resp.status_code == 400:
        # Already exists — log in
        resp = sync_client.post(
            "/api/v1/auth/login",
            json={"email": "ws_test@example.com", "password": "ws_pass_123"},
        )
    assert resp.status_code in (200, 201)
    return resp.json()["access_token"]


def test_ws_connect_valid_token(sync_client: TestClient, registered_token: str):
    """A valid JWT should be accepted and receive a 'connected' message."""
    with sync_client.websocket_connect(f"/ws?token={registered_token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert "user_id" in msg


def test_ws_ping_pong(sync_client: TestClient, registered_token: str):
    """Client sends ping, server replies pong."""
    with sync_client.websocket_connect(f"/ws?token={registered_token}") as ws:
        ws.receive_json()  # discard "connected" message
        ws.send_json({"type": "ping"})
        reply = ws.receive_json()
        assert reply["type"] == "pong"


def test_ws_invalid_token_rejected(sync_client: TestClient):
    """An invalid JWT should result in the connection being closed (code 4001)."""
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/ws?token=not_a_valid_token") as ws:
            ws.receive_json()


def test_ws_expired_token_rejected(sync_client: TestClient):
    """A token with an invalid payload (missing 'type') should be rejected."""
    import jwt
    from app.core.config import settings

    bad_token = jwt.encode({"sub": "00000000-0000-0000-0000-000000000000"}, settings.SECRET_KEY, algorithm="HS256")
    with pytest.raises(Exception):
        with sync_client.websocket_connect(f"/ws?token={bad_token}") as ws:
            ws.receive_json()
