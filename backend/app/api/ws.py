"""
WebSocket endpoint.

Connect:  ws(s)://<host>/ws?token=<access_jwt>

Messages from server:
  {"type": "connected",        "user_id": "..."}
  {"type": "activity.updated", "event_id": "...", "action": "started|paused|stopped|completed", ...}
  {"type": "schedule.updated", "schedule_id": "..."}
  {"type": "sync.complete",    "provider": "notion", "tasks_upserted": 5}
  {"type": "agent.thinking"}

Messages from client:
  {"type": "ping"}  →  server replies {"type": "pong"}
"""

import uuid

import jwt
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import get_db
from app.ws.hub import hub

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
):
    # ── Authenticate ─────────────────────────────────────────────────────────
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise ValueError("not an access token")
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await websocket.close(code=4001)
        return

    # ── Verify user exists ────────────────────────────────────────────────────
    from app.models.user import User

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        await websocket.close(code=4001)
        return

    # ── Register connection ───────────────────────────────────────────────────
    uid_str = str(user_id)
    await hub.connect(uid_str, websocket)

    try:
        await websocket.send_json({"type": "connected", "user_id": uid_str})

        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(uid_str, websocket)
