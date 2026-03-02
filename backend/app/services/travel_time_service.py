"""
Travel time aggregation service.

Pipeline
────────
1. fetch_recent_pings()        — pull the last N pings for a user
2. detect_dwells()             — find periods of stationary activity (clusters)
3. detect_trips()              — extract movement segments between dwell periods
4. upsert_travel_times()       — update TravelTime rows with Welford online statistics

Distance
────────
Haversine formula gives great-circle distance in metres.

Dwell detection (simple)
────────────────────────
A "dwell" is a run of consecutive pings where every ping is within DWELL_RADIUS_M
of the centroid of the run and the total duration is at least DWELL_MIN_MINUTES.

Location clustering
────────────────────
Each unique (origin, destination) pair is matched to existing TravelTime rows
by centroid proximity (CLUSTER_RADIUS_M).  If no match exists a new row is created
with an auto-generated label ("Location 1", "Location 2", …).
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location import LocationPing
from app.models.travel_time import TravelTime

# ── Tuneable parameters ───────────────────────────────────────────────────────

DWELL_RADIUS_M: float = 80.0       # pings within this radius count as the same dwell
DWELL_MIN_MINUTES: float = 8.0     # a dwell must last at least this long
CLUSTER_RADIUS_M: float = 150.0    # two locations are "the same" if their centroids are this close


# ── Haversine ─────────────────────────────────────────────────────────────────


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two (lat, lon) points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class DwellPeriod:
    centroid_lat: float
    centroid_lon: float
    start: datetime
    end: datetime
    ping_count: int


@dataclass
class Trip:
    origin: DwellPeriod
    destination: DwellPeriod
    duration_minutes: float   # time from leaving origin to arriving at destination


# ── Dwell detection ───────────────────────────────────────────────────────────


def detect_dwells(pings: list[LocationPing]) -> list[DwellPeriod]:
    """Segment a chronologically ordered list of pings into dwell periods."""
    if not pings:
        return []

    dwells: list[DwellPeriod] = []
    cluster: list[LocationPing] = [pings[0]]

    for ping in pings[1:]:
        # Centroid of current cluster
        clat = sum(p.latitude for p in cluster) / len(cluster)
        clon = sum(p.longitude for p in cluster) / len(cluster)

        dist = haversine(clat, clon, ping.latitude, ping.longitude)
        if dist <= DWELL_RADIUS_M:
            cluster.append(ping)
        else:
            # Flush existing cluster if it qualifies as a dwell
            _maybe_add_dwell(cluster, dwells)
            cluster = [ping]

    _maybe_add_dwell(cluster, dwells)
    return dwells


def _maybe_add_dwell(cluster: list[LocationPing], out: list[DwellPeriod]) -> None:
    if len(cluster) < 2:
        return
    duration_min = (cluster[-1].pinged_at - cluster[0].pinged_at).total_seconds() / 60
    if duration_min < DWELL_MIN_MINUTES:
        return
    clat = sum(p.latitude for p in cluster) / len(cluster)
    clon = sum(p.longitude for p in cluster) / len(cluster)
    out.append(DwellPeriod(
        centroid_lat=clat,
        centroid_lon=clon,
        start=cluster[0].pinged_at,
        end=cluster[-1].pinged_at,
        ping_count=len(cluster),
    ))


# ── Trip detection ────────────────────────────────────────────────────────────


def detect_trips(dwells: list[DwellPeriod]) -> list[Trip]:
    """Return a Trip for each consecutive dwell pair."""
    trips: list[Trip] = []
    for i in range(len(dwells) - 1):
        origin = dwells[i]
        destination = dwells[i + 1]
        # Travel time = gap between leaving origin and arriving at destination
        gap_minutes = (destination.start - origin.end).total_seconds() / 60
        if gap_minutes > 0:
            trips.append(Trip(origin=origin, destination=destination, duration_minutes=gap_minutes))
    return trips


# ── Welford online mean + variance update ─────────────────────────────────────


def _welford_update(
    count: int,
    mean: float | None,
    m2: float,   # running sum of squared deviations (variance * (n-1))
    new_value: float,
) -> tuple[int, float, float]:
    """Return (new_count, new_mean, new_m2)."""
    count += 1
    mean = mean or 0.0
    delta = new_value - mean
    mean += delta / count
    delta2 = new_value - mean
    m2 += delta * delta2
    return count, mean, m2


# ── DB upsert ─────────────────────────────────────────────────────────────────


async def upsert_travel_times(
    user_id: uuid.UUID, trips: list[Trip], db: AsyncSession
) -> int:
    """Update TravelTime aggregate rows.  Returns number of rows updated/inserted."""
    if not trips:
        return 0

    # Load all existing TravelTime rows for this user
    result = await db.execute(
        select(TravelTime).where(TravelTime.user_id == user_id)
    )
    existing: list[TravelTime] = list(result.scalars().all())

    updated = 0
    next_label_num = len(existing) + 1

    for trip in trips:
        # Skip implausible values (> 4 hours or negative)
        if not (0 < trip.duration_minutes <= 240):
            continue

        row = _find_matching_row(
            existing,
            trip.origin.centroid_lat, trip.origin.centroid_lon,
            trip.destination.centroid_lat, trip.destination.centroid_lon,
        )

        if row is None:
            origin_label = f"Location {next_label_num}"
            next_label_num += 1
            dest_label = f"Location {next_label_num}"
            next_label_num += 1
            row = TravelTime(
                user_id=user_id,
                origin_label=origin_label,
                destination_label=dest_label,
                origin_lat=trip.origin.centroid_lat,
                origin_lon=trip.origin.centroid_lon,
                destination_lat=trip.destination.centroid_lat,
                destination_lon=trip.destination.centroid_lon,
                sample_count=0,
                hourly_means={},
                day_of_week_means={},
            )
            db.add(row)
            existing.append(row)

        # Welford update
        m2 = (row.std_deviation_minutes or 0.0) ** 2 * max(row.sample_count - 1, 0)
        new_count, new_mean, new_m2 = _welford_update(
            row.sample_count, row.mean_duration_minutes, m2, trip.duration_minutes
        )
        row.sample_count = new_count
        row.mean_duration_minutes = new_mean
        row.std_deviation_minutes = math.sqrt(new_m2 / new_count) if new_count > 1 else 0.0
        row.min_duration_minutes = min(
            trip.duration_minutes, row.min_duration_minutes or trip.duration_minutes
        )
        row.max_duration_minutes = max(
            trip.duration_minutes, row.max_duration_minutes or trip.duration_minutes
        )
        row.last_observed_at = trip.destination.start

        # Per-hour and per-day means (simple running average)
        hour_key = str(trip.destination.start.hour)
        day_key = str(trip.destination.start.weekday())
        hourly = dict(row.hourly_means or {})
        daily = dict(row.day_of_week_means or {})
        hourly[hour_key] = _running_avg(hourly.get(hour_key), trip.duration_minutes)
        daily[day_key] = _running_avg(daily.get(day_key), trip.duration_minutes)
        row.hourly_means = hourly
        row.day_of_week_means = daily

        updated += 1

    await db.commit()
    return updated


def _find_matching_row(
    rows: list[TravelTime],
    orig_lat: float, orig_lon: float,
    dest_lat: float, dest_lon: float,
) -> TravelTime | None:
    for row in rows:
        if (
            haversine(orig_lat, orig_lon, row.origin_lat, row.origin_lon) <= CLUSTER_RADIUS_M
            and haversine(dest_lat, dest_lon, row.destination_lat, row.destination_lon) <= CLUSTER_RADIUS_M
        ):
            return row
    return None


def _running_avg(existing: float | None, new_value: float) -> float:
    if existing is None:
        return new_value
    return (existing + new_value) / 2


# ── Entry point called by the Celery worker ───────────────────────────────────


async def aggregate_for_user(user_id: uuid.UUID, db: AsyncSession, lookback_hours: int = 24) -> int:
    """Fetch recent pings, detect trips, upsert TravelTime rows."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    result = await db.execute(
        select(LocationPing)
        .where(LocationPing.user_id == user_id, LocationPing.pinged_at >= cutoff)
        .order_by(LocationPing.pinged_at)
    )
    pings = list(result.scalars().all())
    dwells = detect_dwells(pings)
    trips = detect_trips(dwells)
    return await upsert_travel_times(user_id, trips, db)
