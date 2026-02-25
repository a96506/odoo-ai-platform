"""
Pydantic schemas for API request/response validation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    event_type: str = Field(..., description="create | write | unlink")
    model: str = Field(..., description="Odoo model name e.g. crm.lead")
    record_id: int
    values: dict[str, Any] = Field(default_factory=dict)
    old_values: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None
    user_id: int | None = None


class AutomationResult(BaseModel):
    success: bool
    action: str
    model: str
    record_id: int
    confidence: float = 0.0
    reasoning: str = ""
    changes_made: dict[str, Any] = Field(default_factory=dict)
    needs_approval: bool = False


class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    automation_type: str
    action_name: str
    odoo_model: str
    odoo_record_id: int | None
    status: str
    confidence: float | None
    ai_reasoning: str | None
    tokens_used: int

    model_config = {"from_attributes": True}


class AutomationRuleCreate(BaseModel):
    name: str
    automation_type: str
    action_name: str
    enabled: bool = True
    confidence_threshold: float = 0.85
    auto_approve: bool = False
    auto_approve_threshold: float = 0.95
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationRuleResponse(AutomationRuleCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    audit_log_id: int
    approved: bool
    approved_by: str = "admin"


class DashboardStats(BaseModel):
    total_automations: int = 0
    automations_today: int = 0
    pending_approvals: int = 0
    success_rate: float = 0.0
    tokens_used_today: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    time_saved_minutes: float = 0.0


class HealthResponse(BaseModel):
    status: str
    odoo_connected: bool
    redis_connected: bool
    db_connected: bool
    version: str = "1.0.0"
