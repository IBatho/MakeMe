"""Maps Google Calendar event dicts ↔ NormalisedEvent."""

from datetime import datetime, timezone

from app.integrations.base import NormalisedEvent


def _parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def gcal_event_to_normalised(gcal_event: dict) -> NormalisedEvent:
    start_raw = gcal_event.get("start", {})
    end_raw = gcal_event.get("end", {})
    is_all_day = "date" in start_raw and "dateTime" not in start_raw

    if is_all_day:
        start_dt = datetime.fromisoformat(start_raw["date"] + "T00:00:00+00:00")
        end_dt = datetime.fromisoformat(end_raw["date"] + "T00:00:00+00:00")
    else:
        start_dt = _parse_dt(start_raw.get("dateTime")) or datetime.now(timezone.utc)
        end_dt = _parse_dt(end_raw.get("dateTime")) or start_dt

    return NormalisedEvent(
        source_id=gcal_event["id"],
        title=gcal_event.get("summary", "Untitled"),
        description=gcal_event.get("description"),
        location=gcal_event.get("location"),
        start_time=start_dt,
        end_time=end_dt,
        is_all_day=is_all_day,
        metadata={
            "gcal_id": gcal_event["id"],
            "gcal_etag": gcal_event.get("etag"),
            "html_link": gcal_event.get("htmlLink"),
        },
    )


def normalised_to_gcal_event(event: NormalisedEvent) -> dict:
    body: dict = {"summary": event.title}
    if event.description:
        body["description"] = event.description
    if event.location:
        body["location"] = event.location

    if event.is_all_day:
        body["start"] = {"date": event.start_time.strftime("%Y-%m-%d")}
        body["end"] = {"date": event.end_time.strftime("%Y-%m-%d")}
    else:
        body["start"] = {"dateTime": event.start_time.isoformat(), "timeZone": "UTC"}
        body["end"] = {"dateTime": event.end_time.isoformat(), "timeZone": "UTC"}

    return body
