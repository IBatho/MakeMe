import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import auth, users, tasks, events, schedules, integrations, activity, location, insights
from app.api import ws as ws_router
import app.integrations  # noqa: F401 — registers providers via @register decorators

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the Redis-backed WebSocket subscriber on app startup/shutdown."""
    from app.ws.hub import hub

    subscriber_task = None
    redis_client = None

    try:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await redis_client.ping()
        hub.set_redis(redis_client)
        subscriber_task = asyncio.create_task(hub.run_subscriber(settings.REDIS_URL))
        logger.info("Redis connected — WebSocket hub using Redis pub-sub")
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — WebSocket hub using direct delivery", exc)

    yield

    if subscriber_task:
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass
    if redis_client:
        await redis_client.aclose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(schedules.router, prefix="/api/v1/schedules", tags=["schedules"])
app.include_router(integrations.router, prefix="/api/v1/integrations", tags=["integrations"])
app.include_router(activity.router, prefix="/api/v1/activity", tags=["activity"])
app.include_router(location.router, prefix="/api/v1/location", tags=["location"])
app.include_router(insights.router, prefix="/api/v1/insights", tags=["insights"])
app.include_router(ws_router.router, tags=["websocket"])


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "0.1.0"}
