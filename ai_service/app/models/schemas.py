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


# ---------------------------------------------------------------------------
# Month-End Closing (1.1)
# ---------------------------------------------------------------------------

class ClosingStartRequest(BaseModel):
    period: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM period")
    started_by: str = "admin"


class ClosingStepResponse(BaseModel):
    step_name: str
    step_order: int
    status: str
    items_found: int = 0
    items_resolved: int = 0
    auto_check_result: dict[str, Any] | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class ClosingStatusResponse(BaseModel):
    closing_id: int
    period: str
    status: str
    overall_progress_pct: float = 0.0
    steps: list[ClosingStepResponse] = []
    issues: list[dict[str, Any]] = []
    summary: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ClosingStepCompleteRequest(BaseModel):
    completed_by: str = "admin"
    notes: str | None = None


# ---------------------------------------------------------------------------
# Bank Reconciliation (1.3)
# ---------------------------------------------------------------------------

class ReconciliationStartRequest(BaseModel):
    journal_id: int
    user_id: str = "admin"


class ReconciliationStartResponse(BaseModel):
    session_id: int
    total_lines: int = 0
    auto_matchable: int = 0
    needs_review: int = 0


class MatchSuggestion(BaseModel):
    bank_line_id: int
    bank_ref: str = ""
    bank_amount: float = 0.0
    matched_entry_id: int | None = None
    matched_entry_ref: str = ""
    matched_amount: float = 0.0
    confidence: float = 0.0
    match_type: str = "none"
    reasoning: str = ""


class ReconciliationSuggestionsResponse(BaseModel):
    session_id: int
    suggestions: list[MatchSuggestion] = []
    total: int = 0
    page: int = 1
    limit: int = 20


class ReconciliationMatchRequest(BaseModel):
    bank_line_id: int
    entry_id: int


class ReconciliationMatchResponse(BaseModel):
    matched: bool = True
    session_progress: dict[str, int] = Field(default_factory=dict)


class ReconciliationSkipRequest(BaseModel):
    bank_line_id: int
    reason: str = ""
