"""
Feature vector builder for the LinUCB contextual bandit.

Feature vector x ∈ R^12 for a (task, slot) pair:
  [0-1]  hour of day:  sin(2π·h/24),  cos(2π·h/24)       — cyclical encoding
  [2-3]  day of week:  sin(2π·d/7),   cos(2π·d/7)        — cyclical encoding
  [4-6]  task priority one-hot:        [need, want, like]
  [7]    deadline urgency:             tanh((days_until - 7) / 7) or 0.0
  [8]    historical completion rate at this hour            (from patterns)
  [9]    historical completion rate on this day of week     (from patterns)
  [10]   task duration normalised:     log2(total_min/30) / log2(16), clamped [-1,1]
  [11]   bias term (always 1.0)
"""

from __future__ import annotations

import math
from datetime import date, datetime

FEATURE_DIM = 12


def build_feature_vector(
    task_priority: str,
    task_deadline: date | None,
    task_total_minutes: int,
    slot_start: datetime,
    patterns: dict,
) -> list[float]:
    """Return a FEATURE_DIM-length list of floats for the given (task, slot) pair."""
    h = slot_start.hour
    dow = slot_start.weekday()  # 0=Mon … 6=Sun

    # Cyclical hour encoding
    sin_h = math.sin(2 * math.pi * h / 24)
    cos_h = math.cos(2 * math.pi * h / 24)

    # Cyclical day-of-week encoding
    sin_d = math.sin(2 * math.pi * dow / 7)
    cos_d = math.cos(2 * math.pi * dow / 7)

    # Priority one-hot
    p_need = 1.0 if task_priority == "need" else 0.0
    p_want = 1.0 if task_priority == "want" else 0.0
    p_like = 1.0 if task_priority == "like" else 0.0

    # Deadline urgency: negative means past, positive means far future
    if task_deadline is not None:
        days_until = (task_deadline - slot_start.date()).days
        urgency = math.tanh((days_until - 7) / 7)
    else:
        urgency = 0.0  # no deadline → neutral

    # Historical completion rate by hour
    comp_by_hour: list[float] = patterns.get("completion_by_hour", [])
    hist_hour = comp_by_hour[h] if len(comp_by_hour) > h else 0.5

    # Historical completion rate by day of week
    comp_by_dow: list[float] = patterns.get("completion_by_dow", [])
    hist_dow = comp_by_dow[dow] if len(comp_by_dow) > dow else 0.5

    # Duration (log scale, normalised to roughly [-1, 1])
    minutes = max(task_total_minutes, 1)
    dur_norm = math.log2(minutes / 30) / math.log2(16)
    dur_norm = max(-1.0, min(1.0, dur_norm))

    return [
        sin_h, cos_h,
        sin_d, cos_d,
        p_need, p_want, p_like,
        urgency,
        hist_hour,
        hist_dow,
        dur_norm,
        1.0,  # bias
    ]
