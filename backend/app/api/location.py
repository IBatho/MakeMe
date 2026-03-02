"""
Location API.

POST /location/ping          — record a GPS ping from the mobile app
GET  /location/travel-times  — list learned travel time aggregates for the current user
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.dependencies import get_current_user, get_db
from app.models.location import LocationPing
from app.models.travel_time import TravelTime
from app.models.user import User
from app.schemas.location import LocationPingCreate, LocationPingResponse, TravelTimeResponse

router = APIRouter()


@router.post("/ping", response_model=LocationPingResponse, status_code=status.HTTP_201_CREATED)
async def record_ping(
    body: LocationPingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ping = LocationPing(
        user_id=current_user.id,
        pinged_at=datetime.now(timezone.utc),
        latitude=body.latitude,
        longitude=body.longitude,
        accuracy_meters=body.accuracy_meters,
        event_id=body.event_id,
        context=body.context,
    )
    db.add(ping)
    await db.commit()
    await db.refresh(ping)
    return ping


@router.get("/travel-times", response_model=list[TravelTimeResponse])
async def list_travel_times(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TravelTime)
        .where(TravelTime.user_id == current_user.id)
        .order_by(TravelTime.sample_count.desc())
    )
    return result.scalars().all()
