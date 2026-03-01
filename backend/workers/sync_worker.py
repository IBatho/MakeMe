"""
Integration sync worker.
Phase 2 will implement provider-specific sync logic here.
"""
from workers.celery_app import celery_app


@celery_app.task(name="workers.sync_worker.sync_integration")
def sync_integration(integration_config_id: str) -> dict:
    """Sync tasks/events from a single integration provider for one user."""
    # TODO (Phase 2): load IntegrationConfig, call provider.fetch_tasks() / fetch_events(),
    # upsert into DB, update last_synced_at and sync_cursor.
    return {"status": "not_implemented", "integration_config_id": integration_config_id}
