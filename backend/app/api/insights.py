"""
Insights API: exposes the learned patterns and bandit model state to the mobile app.

GET /insights  — returns human-readable pattern summary for the current user.
"""

from fastapi import APIRouter, Depends

from app.agent.memory import load_memory
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("")
async def get_insights(current_user: User = Depends(get_current_user)) -> dict:
    """
    Return the user's learned patterns and bandit model status.

    The response is intentionally human-readable so the Flutter app can
    display it directly without further processing.
    """
    memory = load_memory(current_user)
    patterns = memory.patterns

    data_points = patterns.get("data_points", 0)
    peak_hours = memory.peak_hours
    dur_ratios = patterns.get("duration_ratio_by_priority", {})
    last_computed = patterns.get("last_computed")

    # Format peak hours as readable strings ("9am", "14:00" → "2pm")
    def _fmt_hour(h: int) -> str:
        if h == 0:
            return "midnight"
        if h < 12:
            return f"{h}am"
        if h == 12:
            return "noon"
        return f"{h - 12}pm"

    peak_hour_labels = [_fmt_hour(h) for h in peak_hours]

    # Day-of-week completion rates
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    comp_by_dow = memory.completion_by_dow
    dow_rates = {
        dow_names[i]: round(comp_by_dow[i], 2)
        for i in range(len(dow_names))
        if i < len(comp_by_dow)
    }

    # Duration accuracy insights
    duration_insights = {}
    for priority, ratio in dur_ratios.items():
        if ratio > 1.1:
            duration_insights[priority] = f"tasks take ~{round((ratio - 1) * 100)}% longer than estimated"
        elif ratio < 0.9:
            duration_insights[priority] = f"tasks finish ~{round((1 - ratio) * 100)}% faster than estimated"
        else:
            duration_insights[priority] = "duration estimates are accurate"

    return {
        "data_points": data_points,
        "bandit_updates": memory.n_bandit_updates,
        "model_warm": memory.n_bandit_updates >= 5,
        "last_pattern_update": last_computed,
        "peak_hours": peak_hour_labels,
        "completion_by_day": dow_rates,
        "duration_accuracy": duration_insights,
        "summary": _build_summary(peak_hour_labels, dow_rates, data_points),
    }


def _build_summary(peak_hours: list[str], dow_rates: dict, data_points: int) -> str:
    if data_points < 5:
        return f"Keep using MakeMe to build your profile. ({data_points} activity logs so far)"

    lines = []
    if peak_hours:
        hours_str = ", ".join(peak_hours[:2])
        lines.append(f"You tend to complete tasks most often at {hours_str}.")

    if dow_rates:
        best_day = max(dow_rates, key=lambda d: dow_rates[d])
        worst_day = min(dow_rates, key=lambda d: dow_rates[d])
        lines.append(
            f"{best_day} is your most productive day; "
            f"{worst_day} has the lowest completion rate."
        )

    return " ".join(lines) if lines else "Not enough data yet."
