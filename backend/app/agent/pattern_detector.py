"""
Pattern detector: mines ActivityLog to learn user habits.

Detected patterns are written to user.preferences["patterns"] and used
as historical features by the LinUCB bandit.

Run via nightly Celery beat task (workers/agent_worker.py).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.event import Event
from app.models.user import User

MIN_DATA_POINTS = 5  # minimum logs before patterns are considered reliable


async def detect_patterns(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Mine the user's ActivityLog and return a patterns dict suitable for
    storage in user.preferences["patterns"].
    """
    result = await db.execute(
        select(ActivityLog, Event)
        .join(Event, ActivityLog.event_id == Event.id, isouter=True)
        .where(
            ActivityLog.user_id == user_id,
            ActivityLog.action.in_(["completed", "stopped"]),
        )
        .order_by(ActivityLog.logged_at)
    )
    rows = result.all()

    if len(rows) < MIN_DATA_POINTS:
        return _empty_patterns(len(rows))

    hour_successes: dict[int, int] = defaultdict(int)
    hour_totals: dict[int, int] = defaultdict(int)
    dow_successes: dict[int, int] = defaultdict(int)
    dow_totals: dict[int, int] = defaultdict(int)
    duration_ratios: dict[str, list[float]] = defaultdict(list)

    for log, event in rows:
        ts: datetime = log.logged_at
        h = ts.hour
        dow = ts.weekday()
        success = log.action == "completed"

        hour_totals[h] += 1
        dow_totals[dow] += 1
        if success:
            hour_successes[h] += 1
            dow_successes[dow] += 1

        # Duration accuracy (actual vs planned)
        if (
            event is not None
            and event.actual_start_time is not None
            and event.actual_end_time is not None
        ):
            planned = (event.end_time - event.start_time).total_seconds() / 60
            actual = (event.actual_end_time - event.actual_start_time).total_seconds() / 60
            if planned > 0:
                ratio = actual / planned
                # Use "want" as fallback since we can't eager-load task priority here
                duration_ratios["want"].append(ratio)

    # Completion rate per hour (0–23), default 0.5 where no data
    comp_by_hour = [
        hour_successes.get(h, 0) / hour_totals[h] if hour_totals.get(h, 0) > 0 else 0.5
        for h in range(24)
    ]

    # Completion rate per day of week (0–6 Mon–Sun)
    comp_by_dow = [
        dow_successes.get(d, 0) / dow_totals[d] if dow_totals.get(d, 0) > 0 else 0.5
        for d in range(7)
    ]

    # Peak hours: top 3 by completion rate (min 1 observation)
    scored = [
        (h, hour_successes.get(h, 0) / hour_totals[h])
        for h in hour_totals
        if hour_totals[h] >= 1
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    peak_hours = [h for h, _ in scored[:3]]

    # Mean duration ratio per priority
    dur_ratio_by_priority = {
        priority: round(sum(ratios) / len(ratios), 2)
        for priority, ratios in duration_ratios.items()
        if ratios
    }

    return {
        "completion_by_hour": comp_by_hour,
        "completion_by_dow": comp_by_dow,
        "peak_hours": peak_hours,
        "duration_ratio_by_priority": dur_ratio_by_priority,
        "data_points": len(rows),
        "last_computed": datetime.now(timezone.utc).isoformat(),
    }


async def update_user_patterns(user: User, db: AsyncSession) -> dict:
    """Detect patterns and persist them to user.preferences. Returns the new patterns."""
    patterns = await detect_patterns(user.id, db)
    prefs = dict(user.preferences or {})
    prefs["patterns"] = patterns
    user.preferences = prefs
    await db.commit()
    return patterns


def _empty_patterns(data_points: int = 0) -> dict:
    return {
        "completion_by_hour": [0.5] * 24,
        "completion_by_dow": [0.5] * 7,
        "peak_hours": [],
        "duration_ratio_by_priority": {},
        "data_points": data_points,
        "last_computed": datetime.now(timezone.utc).isoformat(),
    }
