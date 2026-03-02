"""
LLM advisor: calls Claude to resolve scheduling conflicts.

Only invoked when the bandit model is uncertain — i.e., two or more WANT
tasks have bandit scores within UNCERTAINTY_THRESHOLD of each other.

The LLM returns a ranked order of task IDs; the scheduler places them in
that order using the normal greedy algorithm.  Falls back to the original
order on any error so the scheduler always makes progress.
"""

from __future__ import annotations

import json
from datetime import date

from app.agent.state import SchedulableTask
from app.core.config import settings

UNCERTAINTY_THRESHOLD = 0.05  # min score gap to consider the bandit confident
MIN_TASKS_FOR_LLM = 2         # don't spend an API call for a single task


def tasks_are_uncertain(scores: list[tuple[SchedulableTask, float]]) -> bool:
    """Return True if the top-2 bandit scores are within the uncertainty threshold."""
    if len(scores) < MIN_TASKS_FOR_LLM:
        return False
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)
    return (sorted_scores[0][1] - sorted_scores[1][1]) < UNCERTAINTY_THRESHOLD


async def rank_tasks_by_llm(
    tasks: list[SchedulableTask],
    patterns: dict,
    period_start: date,
    period_end: date,
) -> list[SchedulableTask]:
    """
    Ask Claude (Haiku) to rank competing tasks for scheduling.
    Returns the same list in the suggested order.
    Falls back to the original order on any error.
    """
    if len(tasks) < MIN_TASKS_FOR_LLM or not settings.ANTHROPIC_API_KEY:
        return tasks

    task_descriptions = [
        {
            "id": str(t.id),
            "title": t.title,
            "priority": t.priority,
            "deadline": t.deadline.isoformat() if t.deadline else None,
            "remaining_minutes": t.remaining_minutes,
        }
        for t in tasks
    ]

    peak_hours = patterns.get("peak_hours", [])
    context = (
        f"User's historically productive hours: {peak_hours}."
        if peak_hours
        else "No pattern data yet."
    )

    prompt = (
        f"You are a scheduling assistant. Rank these tasks in the order they should be "
        f"scheduled between {period_start} and {period_end}.\n\n"
        f"Tasks:\n{json.dumps(task_descriptions, indent=2)}\n\n"
        f"User context: {context}\n\n"
        "Rules:\n"
        "- NEED tasks must come first.\n"
        "- Among WANT tasks, prefer those with earlier deadlines.\n"
        "- If deadlines are similar, prefer tasks with fewer remaining minutes (quick wins).\n"
        "- LIKE tasks fill remaining time.\n\n"
        "Respond with ONLY a JSON array of task IDs in the recommended order.\n"
        'Example: ["id1", "id2", "id3"]'
    )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 256,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"].strip()
            ordered_ids: list[str] = json.loads(text)
    except Exception:
        return tasks  # fallback: keep original order

    id_to_task = {str(t.id): t for t in tasks}
    reordered = [id_to_task[tid] for tid in ordered_ids if tid in id_to_task]
    # Append any tasks the LLM did not mention
    mentioned = set(ordered_ids)
    reordered += [t for t in tasks if str(t.id) not in mentioned]
    return reordered
