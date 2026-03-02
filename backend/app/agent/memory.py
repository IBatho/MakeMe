"""
User memory: thin interface over user.preferences for the scheduler.

Provides typed access to the stored bandit model and learned patterns,
keeping the scheduler decoupled from the raw preferences JSONB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.user import User


@dataclass
class UserMemory:
    patterns: dict = field(default_factory=dict)
    bandit_data: dict = field(default_factory=dict)
    n_bandit_updates: int = 0
    peak_hours: list[int] = field(default_factory=list)
    completion_by_hour: list[float] = field(default_factory=lambda: [0.5] * 24)
    completion_by_dow: list[float] = field(default_factory=lambda: [0.5] * 7)


def load_memory(user: User) -> UserMemory:
    """Extract bandit model and pattern data from user.preferences."""
    prefs = user.preferences or {}
    patterns: dict = prefs.get("patterns", {})
    bandit_data: dict = prefs.get("bandit", {})

    return UserMemory(
        patterns=patterns,
        bandit_data=bandit_data,
        n_bandit_updates=bandit_data.get("n_updates", 0),
        peak_hours=patterns.get("peak_hours", []),
        completion_by_hour=patterns.get("completion_by_hour", [0.5] * 24),
        completion_by_dow=patterns.get("completion_by_dow", [0.5] * 7),
    )
