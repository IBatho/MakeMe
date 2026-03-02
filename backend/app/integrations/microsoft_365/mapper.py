"""
Maps between Microsoft Graph API event objects and NormalisedEvent.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.base import NormalisedEvent


def graph_event_to_normalised(item: dict) -> NormalisedEvent:
    """Convert a Microsoft Graph API event object to a NormalisedEvent."""
    title = item.get("subject") or "Untitled"
    description = item.get("bodyPreview") or None
    location = (item.get("location") or {}).get("displayName") or None

    start_dt = _parse_graph_dt(item.get("start", {}))
    end_dt = _parse_graph_dt(item.get("end", {}))
    is_all_day = item.get("isAllDay", False)

    if start_dt is None:
        start_dt = datetime.now(timezone.utc)
    if end_dt is None:
        end_dt = start_dt

    return NormalisedEvent(
        source_id=item.get("id", ""),
        title=title,
        start_time=start_dt,
        end_time=end_dt,
        description=description,
        location=location,
        is_all_day=is_all_day,
        metadata={
            "graph_id": item.get("id", ""),
            "web_link": item.get("webLink", ""),
        },
    )


def normalised_to_graph_event(event: NormalisedEvent) -> dict:
    """Convert a NormalisedEvent to a Microsoft Graph API event request body."""
    body: dict = {
        "subject": event.title,
        "start": {
            "dateTime": event.start_time.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": event.end_time.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "timeZone": "UTC",
        },
        "isAllDay": event.is_all_day,
    }
    if event.description:
        body["body"] = {"contentType": "text", "content": event.description}
    if event.location:
        body["location"] = {"displayName": event.location}
    return body


def _parse_graph_dt(dt_obj: dict) -> datetime | None:
    if not dt_obj:
        return None
    dt_str = dt_obj.get("dateTime", "")
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
