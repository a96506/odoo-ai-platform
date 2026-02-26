"""
Odoo AI Automation Platform — FastAPI entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import get_settings
from app.models.audit import (
    init_db,
    get_session_factory,
    AutomationRule,
)
from app.automations import init_automations
from app.webhooks.handlers import router as webhook_router
from app.routers.health import router as health_router
from app.routers.dashboard import router as dashboard_router
from app.routers.rules import router as rules_router
from app.routers.chat import router as chat_router
from app.routers.insights import router as insights_router
from app.routers.closing import router as closing_router
from app.routers.reconciliation import router as reconciliation_router
from app.routers.deduplication import router as dedup_router
from app.routers.credit import router as credit_router
from app.routers.documents import router as documents_router
from app.routers.digest import router as digest_router
from app.routers.forecast import router as forecast_router
from app.routers.reports import router as reports_router
from app.routers.role_dashboard import router as role_dashboard_router
from app.routers.websocket import router as ws_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_ai_service")
    init_db()
    init_automations()
    seed_default_rules()
    logger.info("ai_service_ready")
    yield
    logger.info("shutting_down_ai_service")


app = FastAPI(
    title="Odoo AI Automation Platform",
    description="AI-powered automation layer for Odoo Enterprise ERP",
    version="1.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(dashboard_router)
app.include_router(rules_router)
app.include_router(chat_router)
app.include_router(insights_router)
app.include_router(closing_router)
app.include_router(reconciliation_router)
app.include_router(dedup_router)
app.include_router(credit_router)
app.include_router(documents_router)
app.include_router(digest_router)
app.include_router(forecast_router)
app.include_router(reports_router)
app.include_router(role_dashboard_router)
app.include_router(ws_router)


def seed_default_rules():
    """Create default automation rules if none exist."""
    Session = get_session_factory()
    session = Session()
    try:
        if session.query(AutomationRule).count() > 0:
            return

        defaults = [
            ("Auto-categorize transactions", "accounting", "categorize_transaction"),
            ("Auto-reconcile bank statements", "accounting", "reconcile_transaction"),
            ("Flag anomalous transactions", "accounting", "flag_anomaly"),
            ("Score leads", "crm", "score_lead"),
            ("Auto-assign leads", "crm", "assign_lead"),
            ("Generate follow-up emails", "crm", "generate_followup"),
            ("Detect duplicate leads", "crm", "detect_duplicates"),
            ("Generate quotations", "sales", "generate_quotation"),
            ("Optimize pricing", "sales", "optimize_pricing"),
            ("Forecast pipeline", "sales", "forecast_pipeline"),
            ("Auto-create purchase orders", "purchase", "auto_create_po"),
            ("Select best vendor", "purchase", "select_vendor"),
            ("Match vendor bills", "purchase", "match_bills"),
            ("Demand forecasting", "inventory", "forecast_demand"),
            ("Auto-reorder stock", "inventory", "auto_reorder"),
            ("Categorize products", "inventory", "categorize_products"),
            ("Auto-approve leaves", "hr", "approve_leave"),
            ("Process expenses", "hr", "process_expense"),
            ("Auto-assign tasks", "project", "assign_task"),
            ("Estimate task duration", "project", "estimate_duration"),
            ("Categorize tickets", "helpdesk", "categorize_ticket"),
            ("Auto-assign tickets", "helpdesk", "assign_ticket"),
            ("Schedule production", "manufacturing", "schedule_production"),
            ("Segment contacts", "marketing", "segment_contacts"),
            ("Month-end closing scan", "month_end", "preclose_scan"),
            ("Month-end closing analysis", "month_end", "closing_analysis"),
            ("Enhanced bank reconciliation", "accounting", "enhanced_reconciliation"),
            ("Weekly deduplication scan", "deduplication", "weekly_scan"),
            ("Duplicate detection on create", "deduplication", "duplicate_check"),
            ("Daily credit scoring", "credit_management", "calculate_scores"),
            ("Credit check on SO", "credit_management", "credit_check"),
            ("Credit hold auto-release", "credit_management", "auto_release"),
            ("Smart invoice processing", "document_processing", "process_document"),
            ("IDP vendor matching", "document_processing", "vendor_match"),
            ("IDP PO validation", "document_processing", "po_validation"),
            ("Daily digest generation", "reporting", "generate_digest"),
            ("Daily digest delivery", "reporting", "deliver_digest"),
            ("Daily cash flow forecast", "forecasting", "generate_forecast"),
            ("Scenario analysis", "forecasting", "scenario_analysis"),
            ("Forecast accuracy tracking", "forecasting", "accuracy_tracking"),
            ("NL report generation", "reporting", "generate_report"),
            ("Scheduled report execution", "reporting", "scheduled_report"),
        ]

        for name, atype, action in defaults:
            rule = AutomationRule(
                name=name,
                automation_type=atype,
                action_name=action,
                enabled=True,
                confidence_threshold=0.85,
                auto_approve=False,
                auto_approve_threshold=0.95,
            )
            session.add(rule)

        session.commit()
        logger.info("seeded_default_rules", count=len(defaults))
    finally:
        session.close()
