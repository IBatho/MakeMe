"""
Integration sync worker — runs on Celery.

Periodic beat schedule: every 15 minutes (configured in celery_app.py).
Can also be triggered on-demand via the POST /integrations/{id}/sync endpoint.
"""

import asyncio
import uuid

from workers.celery_app import celery_app


@celery_app.task(name="workers.sync_worker.sync_integration", bind=True, max_retries=3)
def sync_integration(self, integration_config_id: str) -> dict:
    """Sync tasks/events for a single IntegrationConfig row."""
    return asyncio.run(_async_sync(uuid.UUID(integration_config_id)))


async def _async_sync(integration_config_id: uuid.UUID) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select

    from app.core.config import settings
    from app.models.integration_config import IntegrationConfig
    from app.services.sync_service import sync_integration as _sync

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(
            select(IntegrationConfig).where(IntegrationConfig.id == integration_config_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            return {"status": "error", "detail": "IntegrationConfig not found"}
        if not config.is_enabled:
            return {"status": "skipped", "detail": "Integration is disabled"}

        sync_result = await _sync(config, db)

    await engine.dispose()
    return {
        "status": "ok",
        "tasks_upserted": sync_result.tasks_upserted,
        "events_upserted": sync_result.events_upserted,
        "errors": sync_result.errors,
    }


@celery_app.task(name="workers.sync_worker.sync_all_integrations")
def sync_all_integrations() -> dict:
    """Triggered every 15 minutes by Celery beat — dispatches per-integration tasks."""
    return asyncio.run(_async_sync_all())


async def _async_sync_all() -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select

    from app.core.config import settings
    from app.models.integration_config import IntegrationConfig

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(
            select(IntegrationConfig.id).where(IntegrationConfig.is_enabled == True)
        )
        ids = result.scalars().all()

    await engine.dispose()

    for cfg_id in ids:
        sync_integration.delay(str(cfg_id))

    return {"dispatched": len(ids)}
