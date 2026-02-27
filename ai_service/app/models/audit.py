"""
SQLAlchemy models for AI decision audit trail, automation state, and Phase 1 tables.
"""

from contextlib import contextmanager
from datetime import datetime, date
from typing import Generator

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    DateTime,
    Date,
    JSON,
    Numeric,
    ForeignKey,
    Index,
    UniqueConstraint,
    create_engine,
    Enum as SAEnum,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
import enum

from app.config import get_settings

Base = declarative_base()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


class AutomationType(str, enum.Enum):
    ACCOUNTING = "accounting"
    CRM = "crm"
    SALES = "sales"
    PURCHASE = "purchase"
    INVENTORY = "inventory"
    HR = "hr"
    PROJECT = "project"
    HELPDESK = "helpdesk"
    MANUFACTURING = "manufacturing"
    MARKETING = "marketing"
    CROSS_APP = "cross_app"
    MONTH_END = "month_end"
    DEDUPLICATION = "deduplication"
    CREDIT_MANAGEMENT = "credit_management"
    FORECASTING = "forecasting"
    REPORTING = "reporting"
    DOCUMENT_PROCESSING = "document_processing"
    SUPPLY_CHAIN = "supply_chain"
    AGENT_WORKFLOW = "agent_workflow"


class AgentRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskClassification(str, enum.Enum):
    LOW = "low"
    WATCH = "watch"
    ELEVATED = "elevated"
    CRITICAL = "critical"


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Phase 0 tables
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    automation_type = Column(SAEnum(AutomationType), nullable=False)
    action_name = Column(String(255), nullable=False)
    odoo_model = Column(String(255), nullable=False)
    odoo_record_id = Column(Integer)
    status = Column(SAEnum(ActionStatus), default=ActionStatus.PENDING)
    confidence = Column(Float)
    ai_reasoning = Column(Text)
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)
    executed_at = Column(DateTime)
    approved_by = Column(String(255))
    tokens_used = Column(Integer, default=0)


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    automation_type = Column(SAEnum(AutomationType), nullable=False)
    action_name = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True)
    confidence_threshold = Column(Float, default=0.85)
    auto_approve = Column(Boolean, default=False)
    auto_approve_threshold = Column(Float, default=0.95)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_type = Column(String(50), nullable=False)
    odoo_model = Column(String(255), nullable=False)
    odoo_record_id = Column(Integer)
    payload = Column(JSON)
    processed = Column(Boolean, default=False)
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    error = Column(Text)


# ---------------------------------------------------------------------------
# Phase 1 tables — Month-End Closing (1.1)
# ---------------------------------------------------------------------------

class MonthEndClosing(Base):
    __tablename__ = "month_end_closings"
    __table_args__ = (
        UniqueConstraint("period", name="uq_month_end_period"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    period = Column(String(7), nullable=False)
    status = Column(String(20), default="in_progress")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    started_by = Column(String(255))
    checklist = Column(JSON, default=dict)
    issues_found = Column(JSON, default=list)
    summary = Column(Text)
    lock_date_set = Column(Boolean, default=False)

    steps = relationship("ClosingStep", back_populates="closing", cascade="all, delete-orphan")


class ClosingStep(Base):
    __tablename__ = "closing_steps"
    __table_args__ = (
        Index("idx_closing_steps_closing", "closing_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    closing_id = Column(Integer, ForeignKey("month_end_closings.id", ondelete="CASCADE"), nullable=False)
    step_name = Column(String(100), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(20), default="pending")
    auto_check_result = Column(JSON)
    items_found = Column(Integer, default=0)
    items_resolved = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    completed_by = Column(String(255))
    notes = Column(Text)

    closing = relationship("MonthEndClosing", back_populates="steps")


# ---------------------------------------------------------------------------
# Phase 1 tables — Bank Reconciliation (1.3)
# ---------------------------------------------------------------------------

class ReconciliationSession(Base):
    __tablename__ = "reconciliation_sessions"
    __table_args__ = (
        Index("idx_recon_sessions_status", "status"),
        Index("idx_recon_sessions_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255))
    journal_id = Column(Integer)
    status = Column(String(20), default="active")
    total_lines = Column(Integer, default=0)
    auto_matched = Column(Integer, default=0)
    manually_matched = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    remaining = Column(Integer, default=0)
    learned_rules = Column(JSON, default=list)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


# ---------------------------------------------------------------------------
# Phase 1 tables — IDP / Document Processing (1.4)
# ---------------------------------------------------------------------------

class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"
    __table_args__ = (
        Index("idx_doc_jobs_status", "status"),
        Index("idx_doc_jobs_type", "document_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(500))
    file_type = Column(String(20))
    document_type = Column(String(50))
    status = Column(String(20), default="queued")
    source = Column(String(50), default="upload")
    uploaded_by = Column(String(255))
    extraction_result = Column(JSON)
    matched_po_id = Column(Integer)
    matched_vendor_id = Column(Integer)
    overall_confidence = Column(Numeric(5, 4))
    field_confidences = Column(JSON, default=dict)
    odoo_record_created = Column(Integer)
    odoo_model_created = Column(String(255))
    error_message = Column(Text)
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    corrections = relationship("ExtractionCorrection", back_populates="job", cascade="all, delete-orphan")


class ExtractionCorrection(Base):
    __tablename__ = "extraction_corrections"
    __table_args__ = (
        Index("idx_corrections_job", "job_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("document_processing_jobs.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    original_value = Column(Text)
    corrected_value = Column(Text)
    corrected_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("DocumentProcessingJob", back_populates="corrections")


# ---------------------------------------------------------------------------
# Phase 1 tables — Deduplication (1.5)
# ---------------------------------------------------------------------------

class DeduplicationScan(Base):
    __tablename__ = "deduplication_scans"
    __table_args__ = (
        Index("idx_dedup_scans_type", "scan_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_type = Column(String(50), nullable=False)
    status = Column(String(20), default="running")
    total_records = Column(Integer, default=0)
    duplicates_found = Column(Integer, default=0)
    auto_merged = Column(Integer, default=0)
    pending_review = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    groups = relationship("DuplicateGroup", back_populates="scan", cascade="all, delete-orphan")


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"
    __table_args__ = (
        Index("idx_duplicate_groups_scan", "scan_id"),
        Index("idx_duplicate_groups_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("deduplication_scans.id", ondelete="CASCADE"), nullable=False)
    odoo_model = Column(String(255), nullable=False)
    record_ids = Column(JSON, nullable=False)
    master_record_id = Column(Integer)
    similarity_score = Column(Numeric(5, 4))
    match_fields = Column(JSON, default=list)
    status = Column(String(20), default="pending")
    resolved_at = Column(DateTime)
    resolved_by = Column(String(255))
    resolution = Column(String(20))

    scan = relationship("DeduplicationScan", back_populates="groups")


# ---------------------------------------------------------------------------
# Phase 1 tables — Credit Management (1.6)
# ---------------------------------------------------------------------------

class CreditScore(Base):
    __tablename__ = "credit_scores"
    __table_args__ = (
        Index("idx_credit_scores_customer", "customer_id"),
        Index("idx_credit_scores_hold", "hold_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, nullable=False, unique=True)
    customer_name = Column(String(255))
    credit_score = Column(Numeric(5, 2))
    credit_limit = Column(Numeric(15, 2))
    current_exposure = Column(Numeric(15, 2), default=0)
    overdue_amount = Column(Numeric(15, 2), default=0)
    payment_history_score = Column(Numeric(5, 2))
    order_volume_score = Column(Numeric(5, 2))
    risk_level = Column(String(20), default="normal")
    hold_active = Column(Boolean, default=False)
    hold_reason = Column(Text)
    last_calculated = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Phase 1 tables — Report Builder (1.7)
# ---------------------------------------------------------------------------

class ReportJob(Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        Index("idx_report_jobs_status", "status"),
        Index("idx_report_jobs_schedule", "schedule_cron", postgresql_where="schedule_cron IS NOT NULL"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_text = Column(Text, nullable=False)
    parsed_query = Column(JSON)
    result_data = Column(JSON)
    format = Column(String(20), default="table")
    file_path = Column(String(500))
    schedule_cron = Column(String(100))
    requested_by = Column(String(255))
    status = Column(String(20), default="pending")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


# ---------------------------------------------------------------------------
# Phase 1 tables — Cash Flow Forecasting (1.8)
# ---------------------------------------------------------------------------

class CashForecast(Base):
    __tablename__ = "cash_forecasts"
    __table_args__ = (
        Index("idx_cash_forecasts_dates", "forecast_date", "target_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    forecast_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=False)
    predicted_balance = Column(Numeric(15, 2), nullable=False)
    confidence_low = Column(Numeric(15, 2))
    confidence_high = Column(Numeric(15, 2))
    ar_expected = Column(Numeric(15, 2), default=0)
    ap_expected = Column(Numeric(15, 2), default=0)
    pipeline_expected = Column(Numeric(15, 2), default=0)
    recurring_expected = Column(Numeric(15, 2), default=0)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    scenarios = relationship("ForecastScenario", back_populates="base_forecast")


class ForecastScenario(Base):
    __tablename__ = "forecast_scenarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    adjustments = Column(JSON, nullable=False, default=dict)
    base_forecast_id = Column(Integer, ForeignKey("cash_forecasts.id"))
    result_data = Column(JSON)
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    base_forecast = relationship("CashForecast", back_populates="scenarios")


class ForecastAccuracyLog(Base):
    __tablename__ = "forecast_accuracy_log"
    __table_args__ = (
        Index("idx_forecast_accuracy_date", "target_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    forecast_id = Column(Integer, ForeignKey("cash_forecasts.id"))
    target_date = Column(Date, nullable=False)
    predicted_balance = Column(Numeric(15, 2))
    actual_balance = Column(Numeric(15, 2))
    error_pct = Column(Numeric(8, 4))
    logged_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Phase 1 tables — Daily Digest (1.11)
# ---------------------------------------------------------------------------

class DailyDigest(Base):
    __tablename__ = "daily_digests"
    __table_args__ = (
        Index("idx_digest_date_role", "digest_date", "user_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_role = Column(String(100), nullable=False)
    digest_date = Column(Date, nullable=False)
    content = Column(JSON, nullable=False)
    channels_sent = Column(JSON, default=list)
    delivered = Column(Boolean, default=False)
    generated_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Phase 2 tables — Agent Orchestration (2.1)
# ---------------------------------------------------------------------------

class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("idx_agent_runs_type", "agent_type"),
        Index("idx_agent_runs_status", "status"),
        Index("idx_agent_runs_started", "started_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_type = Column(String(100), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    trigger_id = Column(String(255))
    status = Column(SAEnum(AgentRunStatus), default=AgentRunStatus.PENDING, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    total_steps = Column(Integer, default=0)
    token_usage = Column(Integer, default=0)
    error = Column(Text)
    initial_state = Column(JSON, default=dict)
    final_state = Column(JSON)

    steps = relationship("AgentStep", back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.step_index")
    suspensions = relationship("AgentSuspension", back_populates="run", cascade="all, delete-orphan")


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        Index("idx_agent_steps_run", "agent_run_id"),
        Index("idx_agent_steps_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    step_name = Column(String(100), nullable=False)
    step_index = Column(Integer, nullable=False)
    input_data = Column(JSON)
    output_data = Column(JSON)
    duration_ms = Column(Integer)
    status = Column(SAEnum(AgentStepStatus), default=AgentStepStatus.PENDING, nullable=False)
    claude_tokens_used = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    run = relationship("AgentRun", back_populates="steps")
    decisions = relationship("AgentDecision", back_populates="step", cascade="all, delete-orphan")


class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    __table_args__ = (
        Index("idx_agent_decisions_step", "agent_step_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_step_id = Column(Integer, ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=False)
    prompt_hash = Column(String(64))
    response = Column(JSON)
    confidence = Column(Float)
    tools_used = Column(JSON, default=list)
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    step = relationship("AgentStep", back_populates="decisions")


class AgentSuspension(Base):
    __tablename__ = "agent_suspensions"
    __table_args__ = (
        Index("idx_agent_suspensions_run", "agent_run_id"),
        Index("idx_agent_suspensions_timeout", "timeout_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    resume_condition = Column(String(100), nullable=False)
    resume_data = Column(JSON, default=dict)
    suspended_at_step = Column(String(100))
    timeout_at = Column(DateTime)
    suspended_at = Column(DateTime, default=datetime.utcnow)
    resumed_at = Column(DateTime)

    run = relationship("AgentRun", back_populates="suspensions")


# ---------------------------------------------------------------------------
# Phase 2 tables — Supply Chain Intelligence (2.8)
# ---------------------------------------------------------------------------

class SupplierRiskScore(Base):
    __tablename__ = "supplier_risk_scores"
    __table_args__ = (
        Index("idx_risk_scores_vendor", "vendor_id"),
        Index("idx_risk_scores_classification", "classification"),
        Index("idx_risk_scores_scored_at", "scored_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(Integer, nullable=False)
    vendor_name = Column(String(255))
    score = Column(Numeric(5, 2), nullable=False)
    previous_score = Column(Numeric(5, 2))
    classification = Column(SAEnum(RiskClassification), nullable=False)
    summary = Column(Text)
    scored_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    factors = relationship("SupplierRiskFactor", back_populates="risk_score", cascade="all, delete-orphan")


class SupplierRiskFactor(Base):
    __tablename__ = "supplier_risk_factors"
    __table_args__ = (
        Index("idx_risk_factors_score", "risk_score_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    risk_score_id = Column(Integer, ForeignKey("supplier_risk_scores.id", ondelete="CASCADE"), nullable=False)
    factor_name = Column(String(100), nullable=False)
    weight = Column(Numeric(4, 2), nullable=False)
    raw_value = Column(Numeric(10, 4))
    weighted_score = Column(Numeric(6, 2), nullable=False)
    details = Column(JSON)

    risk_score = relationship("SupplierRiskScore", back_populates="factors")


class DisruptionPrediction(Base):
    __tablename__ = "disruption_predictions"
    __table_args__ = (
        Index("idx_disruption_vendor", "vendor_id"),
        Index("idx_disruption_active", "is_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(Integer, nullable=False)
    vendor_name = Column(String(255))
    prediction_type = Column(String(50), nullable=False)
    probability = Column(Numeric(5, 4), nullable=False)
    estimated_impact = Column(JSON)
    recommended_actions = Column(JSON, default=list)
    supporting_data = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    resolved_at = Column(DateTime)


class SupplyChainAlert(Base):
    __tablename__ = "supply_chain_alerts"
    __table_args__ = (
        Index("idx_sc_alerts_vendor", "vendor_id"),
        Index("idx_sc_alerts_severity", "severity"),
        Index("idx_sc_alerts_resolved", "resolved_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(Integer, nullable=False)
    vendor_name = Column(String(255))
    alert_type = Column(String(50), nullable=False)
    severity = Column(SAEnum(AlertSeverity), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    related_prediction_id = Column(Integer, ForeignKey("disruption_predictions.id"))
    acknowledged_by = Column(String(255))
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class AlternativeSupplierMap(Base):
    __tablename__ = "alternative_supplier_maps"
    __table_args__ = (
        Index("idx_alt_supplier_product", "product_id"),
        Index("idx_alt_supplier_primary", "primary_vendor_id"),
        UniqueConstraint("product_id", "primary_vendor_id", "alternative_vendor_id", name="uq_alt_supplier_mapping"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255))
    primary_vendor_id = Column(Integer, nullable=False)
    primary_vendor_name = Column(String(255))
    alternative_vendor_id = Column(Integer, nullable=False)
    alternative_vendor_name = Column(String(255))
    price_delta_pct = Column(Numeric(6, 2))
    lead_time_delta_days = Column(Integer)
    quality_comparable = Column(Boolean)
    last_evaluated = Column(DateTime, default=datetime.utcnow)
    is_single_source = Column(Boolean, default=False)
    revenue_at_risk = Column(Numeric(15, 2))


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.ai_database_url, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for safe session lifecycle — use in Celery tasks and utilities."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session per request."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
