"""
Activity tracking API.

POST /activity/start   — mark an event as in-progress
POST /activity/stop    — mark an event as stopped/completed
POST /activity/update  — update completion percentage mid-session
GET  /activity         — list recent activity logs
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_current_user, get_db
from app.models.activity_log import ActivityLog
from app.models.event import Event, EventStatus
from app.models.task import Task
from app.models.user import User
from app.schemas.activity import ActivityResponse, ActivityStart, ActivityStop, ActivityUpdate
from app.ws.hub import hub

router = APIRouter()


async def _get_owned_event(event_id: uuid.UUID, user: User, db: AsyncSession) -> Event:
    result = await db.execute(
        select(Event).where(Event.id == event_id, Event.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/start", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def start_activity(
    body: ActivityStart,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await _get_owned_event(body.event_id, current_user, db)

    now = datetime.now(timezone.utc)
    log = ActivityLog(
        user_id=current_user.id,
        event_id=event.id,
        task_id=event.task_id,
        logged_at=now,
        action="started",
        device_id=body.device_id,
    )
    db.add(log)

    event.status = EventStatus.IN_PROGRESS
    if event.actual_start_time is None:
        event.actual_start_time = now

    await db.commit()
    await db.refresh(log)

    await hub.publish(
        str(current_user.id),
        {
            "type": "activity.updated",
            "event_id": str(event.id),
            "action": "started",
            "timestamp": now.isoformat(),
        },
    )

    return log


@router.post("/stop", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def stop_activity(
    body: ActivityStop,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await _get_owned_event(body.event_id, current_user, db)

    now = datetime.now(timezone.utc)
    action = "completed" if body.completion_percentage >= 1.0 else "stopped"

    log = ActivityLog(
        user_id=current_user.id,
        event_id=event.id,
        task_id=event.task_id,
        logged_at=now,
        action=action,
        completion_percentage=body.completion_percentage,
        notes=body.notes,
        device_id=body.device_id,
    )
    db.add(log)

    event.actual_end_time = now
    event.completion_percentage = body.completion_percentage
    event.status = EventStatus.COMPLETED if action == "completed" else EventStatus.CANCELLED

    # Propagate completion to the linked task
    if event.task_id and body.completion_percentage >= 1.0:
        task_result = await db.execute(
            select(Task).where(Task.id == event.task_id, Task.user_id == current_user.id)
        )
        task = task_result.scalar_one_or_none()
        if task:
            task.is_complete = True
            task.completion_percentage = 1.0

    await db.commit()
    await db.refresh(log)

    await hub.publish(
        str(current_user.id),
        {
            "type": "activity.updated",
            "event_id": str(event.id),
            "action": action,
            "completion_percentage": body.completion_percentage,
            "timestamp": now.isoformat(),
        },
    )

    # Trigger incremental agent update (Phase 5 will process the reward signal)
    try:
        from workers.agent_worker import incremental_update

        incremental_update.delay(str(current_user.id), f"activity.{action}")
    except Exception:
        pass

    return log


@router.post("/update", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def update_activity(
    body: ActivityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    event = await _get_owned_event(body.event_id, current_user, db)

    now = datetime.now(timezone.utc)
    log = ActivityLog(
        user_id=current_user.id,
        event_id=event.id,
        task_id=event.task_id,
        logged_at=now,
        action="paused",
        completion_percentage=body.completion_percentage,
        notes=body.notes,
        device_id=body.device_id,
    )
    db.add(log)

    event.completion_percentage = body.completion_percentage

    await db.commit()
    await db.refresh(log)

    await hub.publish(
        str(current_user.id),
        {
            "type": "activity.updated",
            "event_id": str(event.id),
            "action": "paused",
            "completion_percentage": body.completion_percentage,
            "timestamp": now.isoformat(),
        },
    )

    return log


@router.get("", response_model=list[ActivityResponse])
async def list_activity(
    event_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(ActivityLog)
        .where(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.logged_at.desc())
        .limit(limit)
    )
    if event_id is not None:
        q = q.where(ActivityLog.event_id == event_id)
    result = await db.execute(q)
    return result.scalars().all()
