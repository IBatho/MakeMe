"""
Greedy task scheduler — Phase 4 rules + Phase 5 bandit scoring.

Priority tiers (always respected):
  1. NEED  — placed first
  2. WANT  — sorted by bandit score (or deadline if cold-start)
  3. LIKE  — fill remaining space, bandit-scored

Within each tier, when the bandit model is warm (≥5 updates) tasks are
ranked by their UCB score against the first available slot as a proxy.
When the model is cold, falls back to the Phase 4 greedy sort (deadline
ascending).  The LLM advisor is called if the top WANT scores are
indistinguishably close.

Each task may be split across multiple free slots when its remaining
duration exceeds max_block_minutes or no single slot is large enough.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from app.agent.rules import FreeSlot
from app.agent.state import SchedulableTask

if TYPE_CHECKING:
    from app.agent.learner import LinUCBModel

_FAR_FUTURE = date(9999, 12, 31)


@dataclass
class TimeBlock:
    task_id: uuid.UUID
    task_title: str
    start: datetime
    end: datetime


def schedule_tasks(
    tasks: list[SchedulableTask],
    free_slots: list[FreeSlot],
    bandit_model: "LinUCBModel | None" = None,
    patterns: dict | None = None,
) -> list[TimeBlock]:
    """
    Place task blocks into free slots.

    Args:
        tasks:        schedulable tasks from WorldState.
        free_slots:   ordered free time windows from compute_free_slots().
        bandit_model: optional LinUCBModel used to rank within priority tiers.
        patterns:     user.preferences["patterns"] passed to feature builder.
    """
    if not tasks or not free_slots:
        return []

    patterns = patterns or {}
    sorted_tasks = _rank_tasks(tasks, free_slots, bandit_model, patterns)

    remaining: dict[uuid.UUID, int] = {t.id: t.remaining_minutes for t in sorted_tasks}
    slot_cursors: list[datetime] = [s.start for s in free_slots]
    blocks: list[TimeBlock] = []

    for task in sorted_tasks:
        if remaining[task.id] <= 0:
            continue

        for slot_idx, slot in enumerate(free_slots):
            if remaining[task.id] <= 0:
                break

            cursor = slot_cursors[slot_idx]
            if cursor >= slot.end:
                continue

            available = int((slot.end - cursor).total_seconds() // 60)
            if available < task.min_block_minutes:
                continue

            block_minutes = min(remaining[task.id], task.max_block_minutes, available)
            if block_minutes < task.min_block_minutes:
                continue

            block_end = cursor + timedelta(minutes=block_minutes)
            blocks.append(
                TimeBlock(
                    task_id=task.id,
                    task_title=task.title,
                    start=cursor,
                    end=block_end,
                )
            )
            remaining[task.id] -= block_minutes
            slot_cursors[slot_idx] = block_end

    blocks.sort(key=lambda b: b.start)
    return blocks


# ── Internal helpers ──────────────────────────────────────────────────────────

def _deadline_key(task: SchedulableTask) -> tuple[int, date]:
    priority_order = {"need": 0, "want": 1, "like": 2}
    p = priority_order.get(task.priority, 3)
    dl = task.deadline if task.deadline is not None else _FAR_FUTURE
    return (p, dl)


def _rank_tasks(
    tasks: list[SchedulableTask],
    free_slots: list[FreeSlot],
    bandit_model: "LinUCBModel | None",
    patterns: dict,
) -> list[SchedulableTask]:
    """Sort tasks: NEED first, then WANT, then LIKE, with bandit scoring within tiers."""
    # Split into priority buckets
    need_tasks = [t for t in tasks if t.priority == "need"]
    want_tasks = [t for t in tasks if t.priority == "want"]
    like_tasks = [t for t in tasks if t.priority == "like"]

    # NEED: always deadline-sorted (hard constraint, bandit doesn't override)
    need_tasks.sort(key=lambda t: t.deadline or _FAR_FUTURE)

    # WANT + LIKE: bandit-scored if warm, otherwise deadline-sorted
    if bandit_model is not None and not bandit_model.is_cold:
        want_tasks = _bandit_sort(want_tasks, free_slots, bandit_model, patterns)
        like_tasks = _bandit_sort(like_tasks, free_slots, bandit_model, patterns)
    else:
        want_tasks.sort(key=lambda t: t.deadline or _FAR_FUTURE)
        like_tasks.sort(key=lambda t: t.deadline or _FAR_FUTURE)

    return need_tasks + want_tasks + like_tasks


def _bandit_sort(
    tasks: list[SchedulableTask],
    free_slots: list[FreeSlot],
    bandit_model: "LinUCBModel",
    patterns: dict,
) -> list[SchedulableTask]:
    """
    Score each task against the first available slot as a proxy and return
    the list sorted by descending UCB score.
    """
    from app.agent.features import build_feature_vector
    from app.agent.llm_advisor import tasks_are_uncertain

    if not tasks:
        return tasks

    # Use the first slot's start as the representative slot context
    proxy_slot_start = free_slots[0].start if free_slots else datetime.utcnow()

    scored: list[tuple[SchedulableTask, float]] = []
    for task in tasks:
        x = build_feature_vector(
            task_priority=task.priority,
            task_deadline=task.deadline,
            task_total_minutes=task.remaining_minutes,
            slot_start=proxy_slot_start,
            patterns=patterns,
        )
        score = bandit_model.score(x)
        scored.append((task, score))

    # If top scores are too close, the LLM advisor would be called here.
    # We note the flag but don't call async from sync context; the
    # schedule_service does this upstream when needed.
    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored]
