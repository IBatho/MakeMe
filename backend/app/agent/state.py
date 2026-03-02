"""
World-state builder for the rule-based scheduler.

WorldState captures everything the agent needs to place task blocks:
  - The user's wake/sleep window and allowed scheduling days
  - Pre-existing locked / external events that cannot be moved
  - Tasks that still need time allocated
"""

from __future__ import annotations

import uuid
import zoneinfo
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event, EventStatus
from app.models.task import Task
from app.models.user import User


@dataclass
class LockedSlot:
    """An immovable block of time (external calendar event or user-locked event)."""

    start: datetime
    end: datetime
    title: str
    event_id: uuid.UUID


@dataclass
class SchedulableTask:
    """A task that needs time blocks placed in the schedule."""

    id: uuid.UUID
    title: str
    priority: str             # TaskPriority value: "need" | "want" | "like"
    deadline: date | None
    remaining_minutes: int    # total_duration_minutes - already scheduled
    min_block_minutes: int
    max_block_minutes: int


@dataclass
class WorldState:
    user_id: uuid.UUID
    period_start: date
    period_end: date
    wake_hour: int                    # default 8
    sleep_hour: int                   # default 22
    travel_buffer_minutes: int        # default 15
    scheduling_days: list[int]        # 0=Mon … 6=Sun, default all
    locked_slots: list[LockedSlot]
    tasks: list[SchedulableTask]
    tz: str                           # IANA timezone string


async def build_world_state(
    user: User,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> WorldState:
    """Query the DB and build a WorldState for the scheduler."""
    prefs = user.preferences or {}
    wake_hour = int(prefs.get("wake_hour", 8))
    sleep_hour = int(prefs.get("sleep_hour", 22))
    travel_buffer = int(prefs.get("travel_buffer_minutes", 15))
    scheduling_days: list[int] = prefs.get("scheduling_days", list(range(7)))

    tz = zoneinfo.ZoneInfo(user.timezone or "UTC")

    # Period window (aware datetimes) for querying events
    window_start = datetime(
        period_start.year, period_start.month, period_start.day, 0, 0, tzinfo=tz
    )
    window_end = datetime(
        period_end.year, period_end.month, period_end.day, 23, 59, 59, tzinfo=tz
    )

    # Load all non-cancelled/skipped events in the period
    result = await db.execute(
        select(Event).where(
            Event.user_id == user.id,
            Event.start_time >= window_start,
            Event.start_time <= window_end,
            Event.status.notin_([EventStatus.CANCELLED, EventStatus.SKIPPED]),
        )
    )
    all_events: list[Event] = list(result.scalars().all())

    # Locked slots: user-locked events, events from external providers,
    # or any manually created event (not agent-created).
    locked_slots: list[LockedSlot] = []
    for ev in all_events:
        if ev.is_locked or not ev.is_agent_created or ev.provider:
            locked_slots.append(
                LockedSlot(
                    start=ev.start_time,
                    end=ev.end_time,
                    title=ev.title,
                    event_id=ev.id,
                )
            )

    # Compute already-scheduled minutes per task (from current agent-created events)
    scheduled_minutes: dict[uuid.UUID, int] = {}
    for ev in all_events:
        if ev.task_id and ev.is_agent_created:
            dur = int((ev.end_time - ev.start_time).total_seconds() // 60)
            scheduled_minutes[ev.task_id] = scheduled_minutes.get(ev.task_id, 0) + dur

    # Load incomplete tasks
    result = await db.execute(
        select(Task).where(
            Task.user_id == user.id,
            Task.is_complete == False,  # noqa: E712
        )
    )
    raw_tasks: list[Task] = list(result.scalars().all())

    tasks: list[SchedulableTask] = []
    for t in raw_tasks:
        already = scheduled_minutes.get(t.id, 0)
        remaining = t.total_duration_minutes - already
        if remaining <= 0:
            continue
        tasks.append(
            SchedulableTask(
                id=t.id,
                title=t.title,
                priority=t.priority,
                deadline=t.deadline,
                remaining_minutes=remaining,
                min_block_minutes=t.min_block_minutes,
                max_block_minutes=t.max_block_minutes,
            )
        )

    return WorldState(
        user_id=user.id,
        period_start=period_start,
        period_end=period_end,
        wake_hour=wake_hour,
        sleep_hour=sleep_hour,
        travel_buffer_minutes=travel_buffer,
        scheduling_days=scheduling_days,
        locked_slots=locked_slots,
        tasks=tasks,
        tz=user.timezone or "UTC",
    )
