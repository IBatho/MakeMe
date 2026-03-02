"""
Tests for Phase 4: rule-based scheduler.

Covers:
  - Pure unit tests for compute_free_slots (no DB needed)
  - Pure unit tests for schedule_tasks (no DB needed)
  - Integration test: POST /schedules/generate via the API
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.agent.rules import FreeSlot, compute_free_slots
from app.agent.scheduler import TimeBlock, schedule_tasks
from app.agent.state import LockedSlot, SchedulableTask, WorldState

# ── Helpers ───────────────────────────────────────────────────────────────────

UTC = timezone.utc


def _utc(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _base_state(
    period_start: date | None = None,
    period_end: date | None = None,
    locked_slots: list[LockedSlot] | None = None,
    tasks: list[SchedulableTask] | None = None,
) -> WorldState:
    return WorldState(
        user_id=uuid.uuid4(),
        period_start=period_start or date(2025, 1, 6),  # Monday
        period_end=period_end or date(2025, 1, 6),
        wake_hour=8,
        sleep_hour=22,
        travel_buffer_minutes=0,
        scheduling_days=list(range(7)),
        locked_slots=locked_slots or [],
        tasks=tasks or [],
        tz="UTC",
    )


# ── compute_free_slots ────────────────────────────────────────────────────────


def test_free_slots_full_day_no_locked():
    """With no locked slots the whole wake-sleep window is free."""
    state = _base_state()
    slots = compute_free_slots(state)
    assert len(slots) == 1
    assert slots[0].start == _utc(2025, 1, 6, 8)
    assert slots[0].end == _utc(2025, 1, 6, 22)
    assert slots[0].duration_minutes == 14 * 60


def test_free_slots_locked_in_middle():
    """A single locked slot should split the day into two free windows."""
    locked = [
        LockedSlot(
            start=_utc(2025, 1, 6, 10),
            end=_utc(2025, 1, 6, 12),
            title="Meeting",
            event_id=uuid.uuid4(),
        )
    ]
    state = _base_state(locked_slots=locked)
    slots = compute_free_slots(state)
    assert len(slots) == 2
    assert slots[0].start == _utc(2025, 1, 6, 8)
    assert slots[0].end == _utc(2025, 1, 6, 10)
    assert slots[1].start == _utc(2025, 1, 6, 12)
    assert slots[1].end == _utc(2025, 1, 6, 22)


def test_free_slots_travel_buffer():
    """Travel buffer is applied around each locked slot."""
    locked = [
        LockedSlot(
            start=_utc(2025, 1, 6, 10),
            end=_utc(2025, 1, 6, 11),
            title="Dentist",
            event_id=uuid.uuid4(),
        )
    ]
    state = _base_state(locked_slots=locked)
    state.travel_buffer_minutes = 30

    slots = compute_free_slots(state)
    assert len(slots) == 2
    # Buffer before: 10:00 - 30min = 09:30
    assert slots[0].end == _utc(2025, 1, 6, 9, 30)
    # Buffer after: 11:00 + 30min = 11:30
    assert slots[1].start == _utc(2025, 1, 6, 11, 30)


def test_free_slots_skips_unschedulable_days():
    """Days not in scheduling_days are skipped."""
    # 2025-01-06 is Monday (weekday=0)
    state = _base_state()
    state.scheduling_days = [1, 2, 3, 4, 5, 6]  # Tue–Sun (skip Monday)
    slots = compute_free_slots(state)
    assert slots == []


def test_free_slots_multi_day():
    """Two consecutive days both produce free slots."""
    state = _base_state(
        period_start=date(2025, 1, 6),
        period_end=date(2025, 1, 7),
    )
    slots = compute_free_slots(state)
    assert len(slots) == 2
    assert slots[0].start.date() == date(2025, 1, 6)
    assert slots[1].start.date() == date(2025, 1, 7)


def test_free_slots_adjacent_locked_merge():
    """Two adjacent locked slots should merge into one busy interval."""
    locked = [
        LockedSlot(start=_utc(2025, 1, 6, 9), end=_utc(2025, 1, 6, 10), title="A", event_id=uuid.uuid4()),
        LockedSlot(start=_utc(2025, 1, 6, 10), end=_utc(2025, 1, 6, 11), title="B", event_id=uuid.uuid4()),
    ]
    state = _base_state(locked_slots=locked)
    slots = compute_free_slots(state)
    assert len(slots) == 2
    assert slots[0].end == _utc(2025, 1, 6, 9)
    assert slots[1].start == _utc(2025, 1, 6, 11)


# ── schedule_tasks ────────────────────────────────────────────────────────────


def _task(
    priority: str = "want",
    remaining: int = 60,
    min_block: int = 30,
    max_block: int = 120,
    deadline: date | None = None,
) -> SchedulableTask:
    return SchedulableTask(
        id=uuid.uuid4(),
        title=f"Task ({priority})",
        priority=priority,
        deadline=deadline,
        remaining_minutes=remaining,
        min_block_minutes=min_block,
        max_block_minutes=max_block,
    )


def _slot(start_hour: int, end_hour: int) -> FreeSlot:
    return FreeSlot(
        start=_utc(2025, 1, 6, start_hour),
        end=_utc(2025, 1, 6, end_hour),
    )


def test_scheduler_places_single_task():
    tasks = [_task(remaining=60)]
    slots = [_slot(8, 22)]
    blocks = schedule_tasks(tasks, slots)
    assert len(blocks) == 1
    assert (blocks[0].end - blocks[0].start) == timedelta(hours=1)


def test_scheduler_empty_inputs():
    assert schedule_tasks([], [_slot(8, 22)]) == []
    assert schedule_tasks([_task()], []) == []


def test_scheduler_priority_order():
    """NEED tasks must be placed before WANT before LIKE."""
    need = _task(priority="need", remaining=60)
    want = _task(priority="want", remaining=60)
    like = _task(priority="like", remaining=60)
    # Single slot with exactly 3 hours — enough for all three in order
    slots = [_slot(8, 11)]
    blocks = schedule_tasks([like, want, need], slots)
    assert len(blocks) == 3
    # NEED block should be earliest
    assert blocks[0].task_id == need.id
    assert blocks[1].task_id == want.id
    assert blocks[2].task_id == like.id


def test_scheduler_want_sorted_by_deadline():
    """Among WANT tasks, the one with the earlier deadline comes first."""
    later = _task(priority="want", deadline=date(2025, 6, 1))
    earlier = _task(priority="want", deadline=date(2025, 2, 1))
    slots = [_slot(8, 14)]
    blocks = schedule_tasks([later, earlier], slots)
    ids = [b.task_id for b in blocks]
    assert ids[0] == earlier.id
    assert ids[1] == later.id


def test_scheduler_task_split_across_slots():
    """A task larger than one slot should be split into multiple blocks."""
    big_task = _task(remaining=180, min_block=30, max_block=60)
    # Three 60-minute slots
    slots = [_slot(8, 9), _slot(10, 11), _slot(12, 13)]
    blocks = schedule_tasks([big_task], slots)
    total_minutes = sum(int((b.end - b.start).total_seconds() // 60) for b in blocks)
    assert total_minutes == 180


def test_scheduler_respects_max_block():
    """No single block should exceed max_block_minutes."""
    task = _task(remaining=240, min_block=30, max_block=90)
    slots = [_slot(8, 22)]
    blocks = schedule_tasks([task], slots)
    for b in blocks:
        dur = int((b.end - b.start).total_seconds() // 60)
        assert dur <= 90


def test_scheduler_skips_slot_too_small():
    """If the slot is smaller than min_block_minutes, task is not placed there."""
    task = _task(remaining=60, min_block=60)
    # 30-minute slot — too small
    slots = [FreeSlot(start=_utc(2025, 1, 6, 8), end=_utc(2025, 1, 6, 8, 30))]
    blocks = schedule_tasks([task], slots)
    assert blocks == []


def test_scheduler_multiple_tasks_share_slot():
    """Multiple tasks should be placed end-to-end in a single large slot."""
    t1 = _task(remaining=60)
    t2 = _task(remaining=60)
    slots = [_slot(8, 22)]
    blocks = schedule_tasks([t1, t2], slots)
    assert len(blocks) == 2
    # Second block starts where first ends
    assert blocks[1].start == blocks[0].end


# ── API integration test ──────────────────────────────────────────────────────


async def test_generate_schedule_endpoint(client, auth_headers):
    """POST /schedules/generate should create a schedule with agent-created events."""
    # Create a task for the test user
    task_resp = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Write report",
            "priority": "want",
            "total_duration_minutes": 90,
            "min_block_minutes": 30,
            "max_block_minutes": 90,
        },
    )
    assert task_resp.status_code == 201

    resp = await client.post(
        "/api/v1/schedules/generate",
        headers=auth_headers,
        json={"period_start": "2025-01-06", "period_end": "2025-01-06"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["generated_by_agent"] is True
    assert data["status"] == "active"
    assert data["blocks_placed"] >= 1
    assert data["tasks_scheduled"] >= 1


async def test_generate_schedule_invalid_dates(client, auth_headers):
    """period_end before period_start should return 422."""
    resp = await client.post(
        "/api/v1/schedules/generate",
        headers=auth_headers,
        json={"period_start": "2025-01-10", "period_end": "2025-01-05"},
    )
    assert resp.status_code == 422


async def test_generate_schedule_no_tasks(client, auth_headers):
    """Generating a schedule with no tasks should succeed (0 blocks)."""
    resp = await client.post(
        "/api/v1/schedules/generate",
        headers=auth_headers,
        json={"period_start": "2025-01-20", "period_end": "2025-01-20"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["generated_by_agent"] is True
