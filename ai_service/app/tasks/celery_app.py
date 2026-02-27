"""
Celery application configuration for async task processing.
"""

from celery import Celery
from celery.signals import worker_init

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "odoo_ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    include=["app.tasks.celery_tasks"],
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
        "app.tasks.celery_tasks.run_month_end_preclose_scan": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_dedup_scan": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_credit_scoring": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_credit_hold_check": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_daily_digest": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_cash_flow_forecast": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_forecast_accuracy_check": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_scheduled_reports": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_agent_workflow": {"queue": "automations"},
        "app.tasks.celery_tasks.run_supplier_risk_scoring": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_delivery_degradation_check": {"queue": "scheduled"},
        "app.tasks.celery_tasks.run_single_source_scan": {"queue": "scheduled"},
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
        "month-end-preclose-scan": {
            "task": "app.tasks.celery_tasks.run_month_end_preclose_scan",
            "schedule": 86400.0,
            "args": ("",),
            "kwargs": {},
            "options": {"expires": 43200},
        },
        "weekly-dedup-scan": {
            "task": "app.tasks.celery_tasks.run_dedup_scan",
            "schedule": 604800.0,
            "options": {"expires": 86400},
        },
        "daily-credit-scoring": {
            "task": "app.tasks.celery_tasks.run_credit_scoring",
            "schedule": 86400.0,
            "options": {"expires": 43200},
        },
        "credit-hold-release-check": {
            "task": "app.tasks.celery_tasks.run_credit_hold_check",
            "schedule": 3600.0,
            "options": {"expires": 1800},
        },
        "daily-digest-generation": {
            "task": "app.tasks.celery_tasks.run_daily_digest",
            "schedule": 86400.0,
            "options": {"expires": 43200},
        },
        "daily-cash-flow-forecast": {
            "task": "app.tasks.celery_tasks.run_cash_flow_forecast",
            "schedule": 86400.0,
            "options": {"expires": 43200},
        },
        "daily-forecast-accuracy-check": {
            "task": "app.tasks.celery_tasks.run_forecast_accuracy_check",
            "schedule": 86400.0,
            "options": {"expires": 43200},
        },
        "hourly-scheduled-reports": {
            "task": "app.tasks.celery_tasks.run_scheduled_reports",
            "schedule": 3600.0,
            "options": {"expires": 1800},
        },
        # Phase 2 — Supply Chain Intelligence
        "daily-supplier-risk-scoring": {
            "task": "app.tasks.celery_tasks.run_supplier_risk_scoring",
            "schedule": 86400.0,
            "options": {"expires": 43200},
        },
        "delivery-degradation-check": {
            "task": "app.tasks.celery_tasks.run_delivery_degradation_check",
            "schedule": 21600.0,
            "options": {"expires": 10800},
        },
        "weekly-single-source-scan": {
            "task": "app.tasks.celery_tasks.run_single_source_scan",
            "schedule": 604800.0,
            "options": {"expires": 86400},
        },
    },
)


@worker_init.connect
def on_worker_init(**kwargs):
    from app.automations import init_automations
    from app.agents import init_agents
    from app.models.audit import init_db
    init_db()
    init_automations()
    init_agents()

