"""
Schedule service: orchestrates world-state → rule engine → greedy optimizer → DB write.

generate_schedule() is the main entry point.  It:
  1. Builds a WorldState from the DB.
  2. Computes free time slots.
  3. Greedily places task blocks.
  4. Archives any previous active schedule.
  5. Persists a new Schedule row + Event rows for every TimeBlock.
  6. Attempts a best-effort calendar write-back (Google Calendar, etc.).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.learner import load_model
from app.agent.memory import load_memory
from app.agent.rules import compute_free_slots
from app.agent.scheduler import TimeBlock, schedule_tasks
from app.agent.state import WorldState, build_world_state
from app.models.event import Event, EventStatus
from app.models.schedule import Schedule, ScheduleStatus
from app.models.user import User

AGENT_VERSION = "bandit-v1"


async def generate_schedule(
    user: User,
    period_start: date,
    period_end: date,
    db: AsyncSession,
) -> Schedule:
    """
    Full pipeline: world state → free slots → bandit-ranked placement → DB write.
    Returns the newly created (active) Schedule.
    """
    state: WorldState = await build_world_state(user, period_start, period_end, db)
    free_slots = compute_free_slots(state)

    # Load bandit model and patterns for slot scoring (Phase 5)
    memory = load_memory(user)
    bandit_model = load_model(user.preferences or {})
    patterns = memory.patterns

    # Optionally invoke LLM advisor when WANT tasks are bandit-uncertain
    want_tasks = [t for t in state.tasks if t.priority == "want"]
    if want_tasks and not bandit_model.is_cold and free_slots:
        from app.agent.features import build_feature_vector
        from app.agent.llm_advisor import rank_tasks_by_llm, tasks_are_uncertain

        proxy_start = free_slots[0].start
        scores = [
            (
                t,
                bandit_model.score(
                    build_feature_vector(t.priority, t.deadline, t.remaining_minutes, proxy_start, patterns)
                ),
            )
            for t in want_tasks
        ]
        if tasks_are_uncertain(scores):
            reordered_want = await rank_tasks_by_llm(want_tasks, patterns, period_start, period_end)
            # Rebuild state.tasks with the LLM-suggested order
            other_tasks = [t for t in state.tasks if t.priority != "want"]
            state.tasks = [t for t in state.tasks if t.priority == "need"] + reordered_want + [
                t for t in other_tasks if t.priority == "like"
            ]

    blocks = schedule_tasks(state.tasks, free_slots, bandit_model=bandit_model, patterns=patterns)

    # Archive any previous active schedules for this user
    result = await db.execute(
        select(Schedule).where(
            Schedule.user_id == user.id,
            Schedule.status == ScheduleStatus.ACTIVE,
        )
    )
    for old in result.scalars().all():
        old.status = ScheduleStatus.ARCHIVED

    # Confidence = fraction of tasks that got at least one block
    tasks_total = len(state.tasks)
    tasks_scheduled = len({b.task_id for b in blocks})
    confidence = tasks_scheduled / tasks_total if tasks_total > 0 else 1.0

    schedule = Schedule(
        user_id=user.id,
        name=f"AI Schedule {period_start} – {period_end}",
        period_start=period_start,
        period_end=period_end,
        status=ScheduleStatus.ACTIVE,
        generated_by_agent=True,
        agent_version=AGENT_VERSION,
        agent_confidence=round(confidence, 3),
        generation_context={
            "tasks_total": tasks_total,
            "tasks_scheduled": tasks_scheduled,
            "blocks_placed": len(blocks),
            "free_slots_available": len(free_slots),
        },
    )
    db.add(schedule)
    await db.flush()  # populate schedule.id without committing

    for block in blocks:
        db.add(
            Event(
                user_id=user.id,
                task_id=block.task_id,
                schedule_id=schedule.id,
                title=block.task_title,
                start_time=block.start,
                end_time=block.end,
                status=EventStatus.SCHEDULED,
                is_agent_created=True,
                is_locked=False,
            )
        )

    await db.commit()
    await db.refresh(schedule)

    # Best-effort calendar write-back (failure does not abort the response)
    try:
        await _write_back_to_calendar(user, blocks, db)
    except Exception:
        pass

    return schedule


async def _write_back_to_calendar(
    user: User,
    blocks: list[TimeBlock],
    db: AsyncSession,
) -> None:
    """Push newly scheduled blocks to the user's primary calendar integration."""
    from app.integrations.base import NormalisedEvent
    from app.integrations.registry import build_provider
    from app.models.integration_config import IntegrationConfig

    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.user_id == user.id,
            IntegrationConfig.provider.in_(["google_calendar"]),
            IntegrationConfig.is_enabled == True,  # noqa: E712
        )
    )
    config = result.scalars().first()
    if not config:
        return

    provider = build_provider(config)
    for block in blocks:
        await provider.create_event(
            NormalisedEvent(
                source_id="",  # will be filled by provider on creation
                title=block.task_title,
                start_time=block.start,
                end_time=block.end,
                description="Scheduled by MakeMe AI",
            )
        )
