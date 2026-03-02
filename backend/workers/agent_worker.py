"""
AI scheduling agent worker.

Phase 3 — aggregate_location_data: detect trips from GPS pings, update TravelTime rows.
Phase 4 — generate_schedule: rule-based scheduler.
Phase 5 — incremental_update: process reward signal, update LinUCB bandit weights.
"""

import asyncio
import uuid

from workers.celery_app import celery_app


@celery_app.task(name="workers.agent_worker.generate_schedule", bind=True, max_retries=3)
def generate_schedule(self, user_id: str, period_start: str, period_end: str) -> dict:
    """Generate a new schedule for the given user and date range."""
    return asyncio.run(_async_generate_schedule(user_id, period_start, period_end))


async def _async_generate_schedule(
    user_id: str, period_start: str, period_end: str
) -> dict:
    from datetime import date

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.user import User
    from app.services.schedule_service import generate_schedule as _generate

    uid = uuid.UUID(user_id)
    p_start = date.fromisoformat(period_start)
    p_end = date.fromisoformat(period_end)

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(
            select(User).where(User.id == uid, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if not user:
            await engine.dispose()
            return {"status": "error", "detail": "user not found"}

        schedule = await _generate(user=user, period_start=p_start, period_end=p_end, db=db)

    await engine.dispose()
    ctx = schedule.generation_context or {}
    return {
        "status": "ok",
        "schedule_id": str(schedule.id),
        "blocks_placed": ctx.get("blocks_placed", 0),
    }


@celery_app.task(name="workers.agent_worker.incremental_update", bind=True, max_retries=3)
def incremental_update(self, user_id: str, trigger: str) -> dict:
    """
    Triggered after an activity event.

    1. Computes the reward signal from the most recent ActivityLog.
    2. Updates the LinUCB bandit weights in user.preferences.
    3. Keeps TravelTime data fresh via location aggregation.
    """
    aggregate_location_data.delay(user_id)
    return asyncio.run(_async_incremental_update(user_id, trigger))


async def _async_incremental_update(user_id: str, trigger: str) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.agent.features import build_feature_vector
    from app.agent.learner import load_model, save_model
    from app.core.config import settings
    from app.models.activity_log import ActivityLog
    from app.models.event import Event
    from app.models.task import Task
    from app.models.user import User

    uid = uuid.UUID(user_id)
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # Fetch the user
        result = await db.execute(
            select(User).where(User.id == uid, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if not user:
            await engine.dispose()
            return {"status": "error", "detail": "user not found"}

        # Fetch the most recent completed/stopped activity log for this user
        log_result = await db.execute(
            select(ActivityLog)
            .where(
                ActivityLog.user_id == uid,
                ActivityLog.action.in_(["completed", "stopped"]),
            )
            .order_by(ActivityLog.logged_at.desc())
            .limit(1)
        )
        log = log_result.scalar_one_or_none()
        if not log or not log.event_id:
            await engine.dispose()
            return {"status": "skipped", "reason": "no recent activity log"}

        # Fetch the event to get timing + task priority
        event_result = await db.execute(select(Event).where(Event.id == log.event_id))
        event = event_result.scalar_one_or_none()
        if not event:
            await engine.dispose()
            return {"status": "skipped", "reason": "event not found"}

        task_priority = "want"
        task_deadline = None
        task_total_minutes = 60
        if event.task_id:
            task_result = await db.execute(select(Task).where(Task.id == event.task_id))
            task = task_result.scalar_one_or_none()
            if task:
                task_priority = task.priority
                task_deadline = task.deadline
                task_total_minutes = task.total_duration_minutes

        # Compute reward
        reward = _compute_reward(log.action, log.completion_percentage or 0.0)

        # Build feature vector for the event's actual slot
        slot_start = event.actual_start_time or event.start_time
        patterns = (user.preferences or {}).get("patterns", {})
        x = build_feature_vector(
            task_priority=task_priority,
            task_deadline=task_deadline,
            task_total_minutes=task_total_minutes,
            slot_start=slot_start,
            patterns=patterns,
        )

        # Update bandit model
        model = load_model(user.preferences or {})
        model.update(x, reward)
        user.preferences = save_model(model, user.preferences or {})
        await db.commit()

        n_updates = model.n_updates

    await engine.dispose()
    return {
        "status": "ok",
        "user_id": user_id,
        "reward": reward,
        "bandit_updates": n_updates,
    }


def _compute_reward(action: str, completion_pct: float) -> float:
    """Map an ActivityLog action + completion percentage to a scalar reward."""
    if action == "completed":
        return max(0.0, min(1.0, completion_pct))  # [0, 1]
    if action == "stopped":
        return -0.5
    return 0.0  # paused / other — no signal yet


@celery_app.task(name="workers.agent_worker.apply_schedule_reward", bind=True, max_retries=2)
def apply_schedule_reward(self, user_id: str, schedule_id: str, rating: int) -> dict:
    """Distribute a schedule star-rating as per-event bandit rewards."""
    return asyncio.run(_async_apply_schedule_reward(user_id, schedule_id, rating))


async def _async_apply_schedule_reward(
    user_id: str, schedule_id: str, rating: int
) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.agent.features import build_feature_vector
    from app.agent.learner import load_model, save_model
    from app.core.config import settings
    from app.models.event import Event
    from app.models.task import Task
    from app.models.user import User

    # Map star rating to per-event reward
    if rating >= 4:
        reward = 0.5
    elif rating <= 2:
        reward = -0.5
    else:
        reward = 0.0  # 3 stars = neutral

    if reward == 0.0:
        return {"status": "skipped", "reason": "neutral rating"}

    uid = uuid.UUID(user_id)
    sid = uuid.UUID(schedule_id)
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        user_result = await db.execute(
            select(User).where(User.id == uid, User.is_active == True)  # noqa: E712
        )
        user = user_result.scalar_one_or_none()
        if not user:
            await engine.dispose()
            return {"status": "error", "detail": "user not found"}

        events_result = await db.execute(
            select(Event).where(
                Event.user_id == uid,
                Event.schedule_id == sid,
                Event.is_agent_created == True,  # noqa: E712
            )
        )
        events = events_result.scalars().all()

        model = load_model(user.preferences or {})
        patterns = (user.preferences or {}).get("patterns", {})

        updates = 0
        for event in events:
            task_priority = "want"
            task_deadline = None
            task_total_minutes = 60
            if event.task_id:
                task_result = await db.execute(select(Task).where(Task.id == event.task_id))
                task = task_result.scalar_one_or_none()
                if task:
                    task_priority = task.priority
                    task_deadline = task.deadline
                    task_total_minutes = task.total_duration_minutes

            x = build_feature_vector(
                task_priority=task_priority,
                task_deadline=task_deadline,
                task_total_minutes=task_total_minutes,
                slot_start=event.start_time,
                patterns=patterns,
            )
            model.update(x, reward)
            updates += 1

        user.preferences = save_model(model, user.preferences or {})
        await db.commit()

    await engine.dispose()
    return {"status": "ok", "events_updated": updates, "reward": reward}


@celery_app.task(name="workers.agent_worker.detect_patterns", bind=True, max_retries=2)
def detect_patterns_task(self, user_id: str) -> dict:
    """Update pattern data for a single user (nightly beat)."""
    return asyncio.run(_async_detect_patterns(user_id))


async def _async_detect_patterns(user_id: str) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.agent.pattern_detector import update_user_patterns
    from app.core.config import settings
    from app.models.user import User

    uid = uuid.UUID(user_id)
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(
            select(User).where(User.id == uid, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if not user:
            await engine.dispose()
            return {"status": "error", "detail": "user not found"}
        patterns = await update_user_patterns(user, db)

    await engine.dispose()
    return {"status": "ok", "data_points": patterns.get("data_points", 0)}


@celery_app.task(name="workers.agent_worker.detect_all_patterns")
def detect_all_patterns() -> dict:
    """Celery beat task — runs nightly, dispatches pattern detection for all users."""
    return asyncio.run(_async_detect_all_patterns())


async def _async_detect_all_patterns() -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.user import User

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(select(User.id).where(User.is_active == True))  # noqa: E712
        user_ids = result.scalars().all()

    await engine.dispose()

    for uid in user_ids:
        detect_patterns_task.delay(str(uid))

    return {"dispatched": len(user_ids)}


@celery_app.task(name="workers.agent_worker.aggregate_location_data", bind=True, max_retries=2)
def aggregate_location_data(self, user_id: str) -> dict:
    """Detect trips from recent GPS pings and update TravelTime aggregate rows."""
    return asyncio.run(_async_aggregate(uuid.UUID(user_id)))


async def _async_aggregate(user_id: uuid.UUID) -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from app.core.config import settings
    from app.services.travel_time_service import aggregate_for_user

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        updated = await aggregate_for_user(user_id, db)

    await engine.dispose()
    return {"status": "ok", "user_id": str(user_id), "travel_times_updated": updated}


@celery_app.task(name="workers.agent_worker.aggregate_all_location_data")
def aggregate_all_location_data() -> dict:
    """Celery beat task — runs hourly, dispatches per-user aggregation."""
    return asyncio.run(_async_aggregate_all())


async def _async_aggregate_all() -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select

    from app.core.config import settings
    from app.models.user import User

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(select(User.id).where(User.is_active == True))
        user_ids = result.scalars().all()

    await engine.dispose()

    for uid in user_ids:
        aggregate_location_data.delay(str(uid))

    return {"dispatched": len(user_ids)}
