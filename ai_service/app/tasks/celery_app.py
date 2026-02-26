"""
Celery application configuration for async task processing.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "odoo_ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.celery_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=600,
    task_routes={
        "app.tasks.celery_tasks.process_webhook_event": {"queue": "webhooks"},
        "app.tasks.celery_tasks.run_automation": {"queue": "automations"},
        "app.tasks.celery_tasks.scheduled_scan": {"queue": "scheduled"},
    },
    beat_schedule={
        "scan-pending-reconciliations": {
            "task": "app.tasks.celery_tasks.scheduled_scan",
            "schedule": 3600.0,
            "args": ("accounting", "reconcile_transactions"),
        },
        "scan-lead-scoring": {
            "task": "app.tasks.celery_tasks.scheduled_scan",
            "schedule": 1800.0,
            "args": ("crm", "score_leads"),
        },
        "scan-reorder-points": {
            "task": "app.tasks.celery_tasks.scheduled_scan",
            "schedule": 7200.0,
            "args": ("purchase", "check_reorder_points"),
        },
        "scan-demand-forecast": {
            "task": "app.tasks.celery_tasks.scheduled_scan",
            "schedule": 14400.0,
            "args": ("inventory", "forecast_demand"),
        },
        "scan-production-schedule": {
            "task": "app.tasks.celery_tasks.scheduled_scan",
            "schedule": 7200.0,
            "args": ("manufacturing", "schedule_production"),
        },
        "scan-contact-segmentation": {
            "task": "app.tasks.celery_tasks.scheduled_scan",
            "schedule": 86400.0,
            "args": ("marketing", "segment_contacts"),
        },
        "cross-app-intelligence": {
            "task": "app.tasks.celery_tasks.run_cross_app_intelligence",
            "schedule": 21600.0,
        },
    },
)

