"""
Constraint checker and free-slot calculator.

compute_free_slots() takes a WorldState and returns a list of FreeSlot objects —
contiguous windows of time where the agent is allowed to place task blocks.
Each locked slot has a travel buffer applied on both sides before being
subtracted from the daily window.
"""

from __future__ import annotations

import zoneinfo
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.agent.state import WorldState


@dataclass
class FreeSlot:
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def compute_free_slots(state: WorldState) -> list[FreeSlot]:
    """
    For each scheduling day in [period_start, period_end]:
      1. Create a daily window [wake_hour, sleep_hour) in the user's timezone.
      2. Subtract all locked slots (with travel buffer on each side).
      3. Keep gaps of at least 1 minute.

    Returns aware datetimes (in the user's timezone).
    """
    tz = zoneinfo.ZoneInfo(state.tz)
    free: list[FreeSlot] = []
    buf = timedelta(minutes=state.travel_buffer_minutes)

    current: date = state.period_start
    while current <= state.period_end:
        if current.weekday() not in state.scheduling_days:
            current += timedelta(days=1)
            continue

        day_start = datetime(current.year, current.month, current.day, state.wake_hour, 0, tzinfo=tz)
        day_end = datetime(current.year, current.month, current.day, state.sleep_hour, 0, tzinfo=tz)

        # Collect busy intervals that overlap this day's window
        busy: list[list[datetime]] = []
        for slot in state.locked_slots:
            b_start = slot.start - buf
            b_end = slot.end + buf
            # Clip to the day window
            b_start = max(b_start, day_start)
            b_end = min(b_end, day_end)
            if b_start < b_end:
                busy.append([b_start, b_end])

        # Sort and merge overlapping busy intervals
        busy.sort(key=lambda x: x[0])
        merged: list[list[datetime]] = []
        for interval in busy:
            if merged and interval[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], interval[1])
            else:
                merged.append(interval)

        # Gaps between merged busy intervals are free
        cursor = day_start
        for b_start, b_end in merged:
            if cursor < b_start:
                free.append(FreeSlot(start=cursor, end=b_start))
            cursor = max(cursor, b_end)
        if cursor < day_end:
            free.append(FreeSlot(start=cursor, end=day_end))

        current += timedelta(days=1)

    return [s for s in free if s.duration_minutes >= 1]
