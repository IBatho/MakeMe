"""
Maps raw Notion page objects to NormalisedTask.

Expected Notion database property names (case-insensitive fallbacks handled):
  Name / Title / Task   → title (title type)
  Description / Notes   → description (rich_text type)
  Priority              → priority (select: Need/Want/Like or High/Medium/Low)
  Duration / Time (min) → total_duration_minutes (number, minutes)
  Deadline / Due Date / Due → deadline (date type)
  Done / Completed / Status → is_complete (checkbox or select)
"""

from datetime import date
from typing import Any

from app.integrations.base import NormalisedTask

_PRIORITY_MAP: dict[str, str] = {
    "need": "need",
    "want": "want",
    "like": "like",
    "high": "need",
    "medium": "want",
    "low": "like",
    "must": "need",
    "should": "want",
    "could": "like",
}

_DONE_STATUSES = {"done", "completed", "finished", "complete"}


def _rich_text(prop_value: Any) -> str | None:
    """Extract plain text from a Notion rich_text or title property value."""
    items = prop_value if isinstance(prop_value, list) else []
    parts = [block.get("plain_text") or block.get("text", {}).get("content", "") for block in items]
    return " ".join(parts).strip() or None


def _select_name(prop: dict) -> str | None:
    sel = prop.get("select") or prop.get("status")
    return sel.get("name") if sel else None


def _date_start(prop: dict) -> date | None:
    dt = prop.get("date")
    if not dt or not dt.get("start"):
        return None
    # Notion dates: "2024-01-15" or "2024-01-15T10:00:00+00:00"
    return date.fromisoformat(dt["start"][:10])


def _number(prop: dict) -> int | None:
    n = prop.get("number")
    return int(n) if n is not None else None


def _checkbox(prop: dict) -> bool:
    return bool(prop.get("checkbox", False))


def _find_prop(props: dict, *names: str) -> dict | None:
    """Return the first property dict matching any of the given names (case-insensitive)."""
    lower_map = {k.lower(): v for k, v in props.items()}
    for name in names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    return None


def notion_page_to_task(page: dict) -> NormalisedTask:
    props = page.get("properties", {})

    # ── Title ────────────────────────────────────────────────────────────────
    title_prop = _find_prop(props, "Name", "Title", "Task", "name", "title")
    title_items = title_prop.get("title", []) if title_prop else []
    title = _rich_text(title_items) or "Untitled"

    # ── Description ──────────────────────────────────────────────────────────
    desc_prop = _find_prop(props, "Description", "Notes", "description", "notes")
    description = _rich_text(desc_prop.get("rich_text", [])) if desc_prop else None

    # ── Priority ─────────────────────────────────────────────────────────────
    prio_prop = _find_prop(props, "Priority", "priority")
    priority_raw = _select_name(prio_prop) if prio_prop else None
    priority = _PRIORITY_MAP.get(priority_raw.lower(), "want") if priority_raw else "want"

    # ── Duration ─────────────────────────────────────────────────────────────
    dur_prop = _find_prop(props, "Duration", "Time (min)", "Time", "duration")
    duration = _number(dur_prop) if dur_prop else None
    total_duration_minutes = duration if (duration and duration > 0) else 60

    # ── Deadline ─────────────────────────────────────────────────────────────
    dl_prop = _find_prop(props, "Deadline", "Due Date", "Due", "deadline")
    deadline = _date_start(dl_prop) if dl_prop else None

    # ── Completion ───────────────────────────────────────────────────────────
    done_prop = _find_prop(props, "Done", "Completed", "Status", "Checkbox")
    is_complete = False
    if done_prop:
        if "checkbox" in done_prop:
            is_complete = _checkbox(done_prop)
        elif "select" in done_prop or "status" in done_prop:
            name = (_select_name(done_prop) or "").lower()
            is_complete = name in _DONE_STATUSES

    return NormalisedTask(
        source_id=page["id"],
        title=title,
        description=description,
        priority=priority,
        total_duration_minutes=total_duration_minutes,
        deadline=deadline,
        is_complete=is_complete,
        metadata={"notion_page_id": page["id"], "notion_url": page.get("url")},
    )
