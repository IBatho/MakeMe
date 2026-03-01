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
    # Beat schedule (Phase 2+)
    beat_schedule={},
)
