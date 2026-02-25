"""
Odoo AI Automation Platform — FastAPI entry point.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from app.config import get_settings
from app.models.audit import (
    init_db,
    get_session_factory,
    AuditLog,
    AutomationRule,
    ActionStatus,
)
from app.models.schemas import (
    HealthResponse,
    DashboardStats,
    AutomationRuleCreate,
    AutomationRuleResponse,
    ApprovalRequest,
    AuditLogResponse,
)
from app.webhooks.handlers import router as webhook_router
from app.automations import init_automations
from app.tasks.celery_tasks import execute_approved_action
from app.chat import get_or_create_session
from app.automations.cross_app import CrossAppIntelligence

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
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    odoo_ok = False
    redis_ok = False
    db_ok = False

    try:
        from app.odoo_client import get_odoo_client

        client = get_odoo_client()
        client.version()
        odoo_ok = True
    except Exception:
        pass

    try:
        import redis as redis_lib

        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url)
        r.ping()
        redis_ok = True
    except Exception:
        pass

    try:
        Session = get_session_factory()
        session = Session()
        session.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )
        session.close()
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if all([odoo_ok, redis_ok, db_ok]) else "degraded",
        odoo_connected=odoo_ok,
        redis_connected=redis_ok,
        db_connected=db_ok,
    )


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------


@app.get("/api/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    Session = get_session_factory()
    session = Session()
    try:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        total = session.query(AuditLog).count()
        today_count = (
            session.query(AuditLog).filter(AuditLog.timestamp >= today).count()
        )
        pending = (
            session.query(AuditLog)
            .filter(AuditLog.status == ActionStatus.PENDING)
            .count()
        )
        executed = (
            session.query(AuditLog)
            .filter(AuditLog.status == ActionStatus.EXECUTED)
            .count()
        )
        success_rate = (executed / total * 100) if total > 0 else 0.0

        from sqlalchemy import func

        tokens_today = (
            session.query(func.coalesce(func.sum(AuditLog.tokens_used), 0))
            .filter(AuditLog.timestamp >= today)
            .scalar()
        )

        by_type = {}
        type_counts = (
            session.query(AuditLog.automation_type, func.count(AuditLog.id))
            .group_by(AuditLog.automation_type)
            .all()
        )
        for atype, count in type_counts:
            by_type[atype] = count

        # Estimate ~2 minutes saved per automation
        time_saved = executed * 2.0

        return DashboardStats(
            total_automations=total,
            automations_today=today_count,
            pending_approvals=pending,
            success_rate=round(success_rate, 1),
            tokens_used_today=tokens_today,
            by_type=by_type,
            time_saved_minutes=time_saved,
        )
    finally:
        session.close()


@app.get("/api/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    automation_type: str | None = None,
):
    Session = get_session_factory()
    session = Session()
    try:
        query = session.query(AuditLog).order_by(AuditLog.timestamp.desc())
        if status:
            query = query.filter(AuditLog.status == status)
        if automation_type:
            query = query.filter(AuditLog.automation_type == automation_type)
        logs = query.offset(offset).limit(limit).all()
        return [AuditLogResponse.model_validate(log) for log in logs]
    finally:
        session.close()


@app.post("/api/approve")
async def approve_action(request: ApprovalRequest):
    Session = get_session_factory()
    session = Session()
    try:
        audit = session.get(AuditLog, request.audit_log_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Audit log not found")
        if audit.status != ActionStatus.PENDING:
            raise HTTPException(status_code=400, detail="Action is not pending")

        if request.approved:
            audit.status = ActionStatus.APPROVED
            audit.approved_by = request.approved_by
            session.commit()
            execute_approved_action.delay(audit.id)
            return {"status": "approved", "message": "Action queued for execution"}
        else:
            audit.status = ActionStatus.REJECTED
            audit.approved_by = request.approved_by
            session.commit()
            return {"status": "rejected"}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Automation Rules CRUD
# ---------------------------------------------------------------------------


@app.get("/api/rules", response_model=list[AutomationRuleResponse])
async def list_rules():
    Session = get_session_factory()
    session = Session()
    try:
        rules = session.query(AutomationRule).all()
        return [AutomationRuleResponse.model_validate(r) for r in rules]
    finally:
        session.close()


@app.post("/api/rules", response_model=AutomationRuleResponse)
async def create_rule(rule: AutomationRuleCreate):
    Session = get_session_factory()
    session = Session()
    try:
        db_rule = AutomationRule(**rule.model_dump())
        session.add(db_rule)
        session.commit()
        session.refresh(db_rule)
        return AutomationRuleResponse.model_validate(db_rule)
    finally:
        session.close()


@app.put("/api/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_rule(rule_id: int, rule: AutomationRuleCreate):
    Session = get_session_factory()
    session = Session()
    try:
        db_rule = session.get(AutomationRule, rule_id)
        if not db_rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        for key, value in rule.model_dump().items():
            setattr(db_rule, key, value)
        session.commit()
        session.refresh(db_rule)
        return AutomationRuleResponse.model_validate(db_rule)
    finally:
        session.close()


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: int):
    Session = get_session_factory()
    session = Session()
    try:
        db_rule = session.get(AutomationRule, rule_id)
        if not db_rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        session.delete(db_rule)
        session.commit()
        return {"status": "deleted"}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------


@app.post("/api/trigger/{automation_type}/{action}")
async def trigger_automation(
    automation_type: str, action: str, model: str, record_id: int
):
    """Manually trigger an automation action on a specific record."""
    from app.tasks.celery_tasks import run_automation

    run_automation.delay(automation_type, action, record_id, model)
    return {"status": "queued", "automation_type": automation_type, "action": action}


# ---------------------------------------------------------------------------
# Natural Language Chat Interface
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    message: str
    session_id: str = "default"


class ChatConfirm(BaseModel):
    session_id: str = "default"
    confirmed: bool = True


@app.post("/api/chat")
async def chat(msg: ChatMessage):
    """Send a natural language message to interact with Odoo."""
    session = get_or_create_session(msg.session_id)
    result = session.send_message(msg.message)
    return result


@app.post("/api/chat/confirm")
async def chat_confirm(req: ChatConfirm):
    """Confirm or reject pending write actions from the chat."""
    session = get_or_create_session(req.session_id)
    result = session.confirm_actions(req.confirmed)
    return result


# ---------------------------------------------------------------------------
# Cross-App Intelligence
# ---------------------------------------------------------------------------


@app.get("/api/insights")
async def get_cross_app_insights():
    """Run cross-module intelligence analysis and return insights."""
    intelligence = CrossAppIntelligence()
    result = intelligence.run_full_analysis()
    return result


# ---------------------------------------------------------------------------
# Seed defaults
# ---------------------------------------------------------------------------


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
