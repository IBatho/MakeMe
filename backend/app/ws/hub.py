"""
WebSocket hub — singleton that manages all live WebSocket connections.

Architecture
────────────
• API handlers call hub.publish(user_id, message) when something changes.
• If Redis is available, the message is pushed to channel "ws:user:{user_id}".
  A background subscriber task receives it and fan-outs to every local WebSocket
  for that user — this works correctly across multiple API processes.
• If Redis is unavailable (e.g. in tests / dev without Redis), the hub falls back
  to delivering directly to local connections.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._redis: "aioredis.Redis | None" = None

    def set_redis(self, client: "aioredis.Redis") -> None:
        self._redis = client

    # ── Connection management ────────────────────────────────────────────────

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, set()).add(ws)
        logger.debug("WS connected user=%s total_conns=%d", user_id, len(self._connections[user_id]))

    async def disconnect(self, user_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(user_id, set())
        conns.discard(ws)
        if not conns:
            self._connections.pop(user_id, None)

    # ── Message delivery ─────────────────────────────────────────────────────

    async def _broadcast(self, user_id: str, message: dict) -> None:
        """Deliver directly to all local WebSocket connections for a user."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(user_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)

    async def publish(self, user_id: str, message: dict) -> None:
        """Publish a message for a user.  Uses Redis if available, otherwise delivers directly."""
        if self._redis:
            try:
                await self._redis.publish(f"ws:user:{user_id}", json.dumps(message))
                return
            except Exception as exc:
                logger.warning("Redis publish failed (%s) — falling back to direct delivery", exc)
        await self._broadcast(user_id, message)

    # ── Redis subscriber (runs as background asyncio task) ───────────────────

    async def run_subscriber(self, redis_url: str) -> None:
        """Subscribe to ws:user:* and forward messages to local connections.

        This task runs for the lifetime of the process.  If Redis disconnects,
        it retries with exponential back-off.
        """
        import redis.asyncio as aioredis

        delay = 1.0
        while True:
            client: "aioredis.Redis | None" = None
            try:
                client = aioredis.from_url(redis_url)
                pubsub = client.pubsub()
                await pubsub.psubscribe("ws:user:*")
                delay = 1.0  # reset on successful connect
                logger.info("WS Redis subscriber connected")
                async for raw in pubsub.listen():
                    if raw["type"] not in ("pmessage", "message"):
                        continue
                    channel = raw["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()
                    # channel = "ws:user:{user_id}"
                    user_id = channel.split(":")[-1]
                    try:
                        data = json.loads(raw["data"])
                        await self._broadcast(user_id, data)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("WS Redis subscriber error (%s) — retrying in %.0fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)
            finally:
                if client:
                    try:
                        await client.aclose()
                    except Exception:
                        pass


# Module-level singleton used everywhere in the app
hub = WebSocketHub()
