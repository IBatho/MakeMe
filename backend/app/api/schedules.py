import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_db, get_current_user
from app.models.schedule import Schedule, ScheduleStatus
from app.models.user import User
from app.schemas.schedule import (
    GenerateScheduleRequest,
    GenerateScheduleResponse,
    RateScheduleRequest,
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
)

router = APIRouter()


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    schedule_status: Optional[ScheduleStatus] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Schedule)
        .where(Schedule.user_id == current_user.id)
        .order_by(Schedule.period_start.desc())
    )
    if schedule_status is not None:
        q = q.where(Schedule.status == schedule_status)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/current", response_model=ScheduleResponse)
async def get_current_schedule(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Schedule)
        .where(Schedule.user_id == current_user.id, Schedule.status == ScheduleStatus.ACTIVE)
        .order_by(Schedule.period_start.desc())
    )
    schedule = result.scalars().first()
    if not schedule:
        raise HTTPException(status_code=404, detail="No active schedule found")
    return schedule


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    schedule = Schedule(user_id=current_user.id, **body.model_dump())
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Schedule).where(
            Schedule.id == schedule_id, Schedule.user_id == current_user.id
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("/generate", response_model=GenerateScheduleResponse, status_code=status.HTTP_201_CREATED)
async def generate_schedule(
    body: GenerateScheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run the AI scheduler for the given date range.

    The agent builds a world state from the user's tasks and locked events,
    computes free slots, and greedily places task blocks.  Previous active
    schedules are archived.  The new schedule is returned immediately; events
    are written to the DB and (best-effort) to any connected calendar.
    """
    from app.services.schedule_service import generate_schedule as _generate

    # Publish an "agent thinking" WebSocket message before the (synchronous) run
    from app.ws.hub import hub
    await hub.publish(str(current_user.id), {"type": "agent.thinking"})

    schedule = await _generate(
        user=current_user,
        period_start=body.period_start,
        period_end=body.period_end,
        db=db,
    )

    ctx = schedule.generation_context or {}
    return GenerateScheduleResponse(
        **ScheduleResponse.model_validate(schedule).model_dump(),
        tasks_total=ctx.get("tasks_total", 0),
        tasks_scheduled=ctx.get("tasks_scheduled", 0),
        blocks_placed=ctx.get("blocks_placed", 0),
    )


@router.post("/{schedule_id}/rate", response_model=ScheduleResponse)
async def rate_schedule(
    schedule_id: uuid.UUID,
    body: RateScheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a 1–5 star rating for a schedule.

    Persists the rating and triggers a background Celery task that
    distributes the reward signal across all agent-created events in the
    schedule, updating the LinUCB bandit weights.
    """
    result = await db.execute(
        select(Schedule).where(
            Schedule.id == schedule_id, Schedule.user_id == current_user.id
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule.user_rating = body.rating
    if body.feedback_text is not None:
        schedule.user_feedback_text = body.feedback_text

    await db.commit()
    await db.refresh(schedule)

    # Dispatch bandit reward update in background
    try:
        from workers.agent_worker import apply_schedule_reward
        apply_schedule_reward.delay(
            str(current_user.id), str(schedule_id), body.rating
        )
    except Exception:
        pass

    return schedule


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: uuid.UUID,
    body: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Schedule).where(
            Schedule.id == schedule_id, Schedule.user_id == current_user.id
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

    await db.commit()
    await db.refresh(schedule)
    return schedule
