"""
Maps between CalDAV/iCalendar VEVENT objects and NormalisedEvent.

Uses the `icalendar` library for parsing (.ics / VCALENDAR text).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from icalendar import Calendar, Event as VEvent, vDatetime

from app.integrations.base import NormalisedEvent


def vevent_to_normalised(vevent: VEvent, source_id: str) -> NormalisedEvent:
    """Convert an icalendar VEVENT component to a NormalisedEvent."""
    title = str(vevent.get("SUMMARY", "Untitled"))
    description = str(vevent.get("DESCRIPTION", "")) or None
    location = str(vevent.get("LOCATION", "")) or None

    # DTSTART / DTEND — may be date-only (all-day) or datetime
    dtstart = vevent.get("DTSTART")
    dtend = vevent.get("DTEND")

    start_dt = _to_aware_datetime(dtstart.dt if dtstart else None)
    end_dt = _to_aware_datetime(dtend.dt if dtend else None)

    # Detect all-day events (date-only DTSTART)
    is_all_day = dtstart is not None and not isinstance(dtstart.dt, datetime)

    if start_dt is None:
        start_dt = datetime.now(timezone.utc)
    if end_dt is None:
        end_dt = start_dt

    return NormalisedEvent(
        source_id=source_id,
        title=title,
        start_time=start_dt,
        end_time=end_dt,
        description=description,
        location=location,
        is_all_day=is_all_day,
    )


def normalised_to_ical(event: NormalisedEvent, uid: str | None = None) -> bytes:
    """Serialise a NormalisedEvent to an iCalendar VCALENDAR bytes string."""
    cal = Calendar()
    cal.add("VERSION", "2.0")
    cal.add("PRODID", "-//MakeMe//MakeMe//EN")

    vevent = VEvent()
    vevent.add("UID", uid or str(uuid.uuid4()))
    vevent.add("SUMMARY", event.title)
    if event.description:
        vevent.add("DESCRIPTION", event.description)
    if event.location:
        vevent.add("LOCATION", event.location)
    vevent.add("DTSTART", event.start_time)
    vevent.add("DTEND", event.end_time)

    cal.add_component(vevent)
    return cal.to_ical()


def parse_ical_events(ical_text: str | bytes) -> list[tuple[str, VEvent]]:
    """
    Parse iCalendar text and return (uid, vevent) pairs for all VEVENT components.
    """
    cal = Calendar.from_ical(ical_text)
    results = []
    for component in cal.walk():
        if component.name == "VEVENT":
            uid = str(component.get("UID", ""))
            results.append((uid, component))
    return results


def _to_aware_datetime(dt) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    # date-only (all-day)
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
