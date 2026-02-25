"""
SQLAlchemy models for AI decision audit trail and automation state.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    Boolean,
    DateTime,
    JSON,
    create_engine,
    Enum as SAEnum,
)
from sqlalchemy.orm import declarative_base, sessionmaker
import enum

from app.config import get_settings

Base = declarative_base()


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


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
