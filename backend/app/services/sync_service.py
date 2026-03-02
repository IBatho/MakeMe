"""
Sync service: fetches tasks/events from an integration provider and upserts them
into the local DB.  Called both from the API endpoint (on-demand) and from the
Celery periodic worker (every 15 min).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.base import NormalisedTask, NormalisedEvent
from app.integrations.registry import build_provider
from app.models.event import Event, EventStatus
from app.models.integration_config import IntegrationConfig
from app.models.task import Task
from app.schemas.integration import SyncResult


async def sync_integration(config: IntegrationConfig, db: AsyncSession) -> SyncResult:
    """Run a full sync for one IntegrationConfig row and persist changes to DB."""
    result = SyncResult()

    try:
        provider = build_provider(config)

        # ── Tasks ────────────────────────────────────────────────────────────
        if provider.provider_type in ("task_source", "both"):
            try:
                normalised_tasks = await provider.fetch_tasks()
                for nt in normalised_tasks:
                    await _upsert_task(config, nt, db)
                    result.tasks_upserted += 1
            except Exception as exc:
                result.errors.append(f"fetch_tasks: {exc}")

        # ── Events ───────────────────────────────────────────────────────────
        if provider.provider_type in ("calendar", "both"):
            try:
                now = datetime.now(timezone.utc)
                # Sync a 60-day window: 7 days back, 53 days forward
                window_start = now - timedelta(days=7)
                window_end = now + timedelta(days=53)
                normalised_events = await provider.fetch_events(window_start, window_end)
                for ne in normalised_events:
                    await _upsert_event(config, ne, db)
                    result.events_upserted += 1
            except Exception as exc:
                result.errors.append(f"fetch_events: {exc}")

        # ── Update sync metadata ─────────────────────────────────────────────
        config.last_synced_at = datetime.now(timezone.utc)
        config.last_sync_status = "error" if result.errors else "success"
        config.last_sync_error = "; ".join(result.errors) if result.errors else None
        await db.commit()

    except Exception as exc:
        config.last_sync_status = "error"
        config.last_sync_error = str(exc)
        await db.commit()
        result.errors.append(str(exc))

    return result


async def _upsert_task(
    config: IntegrationConfig, nt: NormalisedTask, db: AsyncSession
) -> None:
    """Insert or update a Task row based on (user_id, source, source_id)."""
    existing = await db.execute(
        select(Task).where(
            Task.user_id == config.user_id,
            Task.source == config.provider,
            Task.source_id == nt.source_id,
        )
    )
    task = existing.scalar_one_or_none()

    if task:
        task.title = nt.title
        task.description = nt.description
        task.priority = nt.priority
        task.total_duration_minutes = nt.total_duration_minutes
        task.deadline = nt.deadline
        task.is_complete = nt.is_complete
        if nt.is_complete and task.completion_percentage < 1.0:
            task.completion_percentage = 1.0
        task.metadata_ = nt.metadata
    else:
        task = Task(
            user_id=config.user_id,
            title=nt.title,
            description=nt.description,
            priority=nt.priority,
            total_duration_minutes=nt.total_duration_minutes,
            min_block_minutes=nt.min_block_minutes,
            max_block_minutes=nt.max_block_minutes,
            deadline=nt.deadline,
            window_start=nt.window_start,
            window_end=nt.window_end,
            is_complete=nt.is_complete,
            completion_percentage=1.0 if nt.is_complete else 0.0,
            source=config.provider,
            source_id=nt.source_id,
            metadata_=nt.metadata,
        )
        db.add(task)


async def _upsert_event(
    config: IntegrationConfig, ne: NormalisedEvent, db: AsyncSession
) -> None:
    """Insert or update an Event row based on (user_id, provider, provider_event_id)."""
    existing = await db.execute(
        select(Event).where(
            Event.user_id == config.user_id,
            Event.provider == config.provider,
            Event.provider_event_id == ne.source_id,
        )
    )
    event = existing.scalar_one_or_none()

    if event:
        event.title = ne.title
        event.description = ne.description
        event.location = ne.location
        event.start_time = ne.start_time
        event.end_time = ne.end_time
        event.is_all_day = ne.is_all_day
        event.metadata_ = ne.metadata
    else:
        event = Event(
            user_id=config.user_id,
            title=ne.title,
            description=ne.description,
            location=ne.location,
            start_time=ne.start_time,
            end_time=ne.end_time,
            is_all_day=ne.is_all_day,
            status=EventStatus.SCHEDULED,
            provider=config.provider,
            provider_event_id=ne.source_id,
            metadata_=ne.metadata,
        )
        db.add(event)
