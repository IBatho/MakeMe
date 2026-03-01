"""
AI scheduling agent worker.
Phase 4 will implement rule-based scheduling;
Phase 5 will add the LinUCB bandit and continuous learning.
"""
from workers.celery_app import celery_app


@celery_app.task(name="workers.agent_worker.generate_schedule")
def generate_schedule(user_id: str, period_start: str, period_end: str) -> dict:
    """Generate a new schedule for the given user and date range."""
    # TODO (Phase 4): build world state, run rule engine, run optimizer, write back to calendar.
    return {"status": "not_implemented", "user_id": user_id}


@celery_app.task(name="workers.agent_worker.incremental_update")
def incremental_update(user_id: str, trigger: str) -> dict:
    """Triggered after an activity event; re-optimises the schedule and feeds reward signal."""
    # TODO (Phase 5): compute reward from ActivityLog, update bandit weights, re-schedule if needed.
    return {"status": "not_implemented", "user_id": user_id, "trigger": trigger}
