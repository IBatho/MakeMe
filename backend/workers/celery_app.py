from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "makeme",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "workers.sync_worker",
        "workers.agent_worker",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sync-all-integrations-every-15-min": {
            "task": "workers.sync_worker.sync_all_integrations",
            "schedule": 900,  # 15 minutes
        },
        "aggregate-location-data-hourly": {
            "task": "workers.agent_worker.aggregate_all_location_data",
            "schedule": 3600,  # 1 hour
        },
        "detect-patterns-nightly": {
            "task": "workers.agent_worker.detect_all_patterns",
            "schedule": 86400,  # 24 hours
        },
    },
)
