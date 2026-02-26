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


# ---------------------------------------------------------------------------
# Cross-Entity Deduplication (1.5)
# ---------------------------------------------------------------------------

class DedupScanRequest(BaseModel):
    scan_type: str = Field(..., description="Entity to scan: res.partner, crm.lead, product.template")


class DedupGroupResponse(BaseModel):
    id: int | None = None
    odoo_model: str
    record_ids: list[int]
    master_record_id: int | None = None
    similarity_score: float = 0.0
    match_fields: list[str] = []
    status: str = "pending"
    records: list[dict[str, Any]] = []

    model_config = {"from_attributes": True}


class DedupScanResponse(BaseModel):
    scan_id: int
    scan_type: str
    status: str = "completed"
    total_records: int = 0
    duplicates_found: int = 0
    groups: list[DedupGroupResponse] = []


class DedupFullScanResponse(BaseModel):
    entity_results: dict[str, DedupScanResponse] = {}
    total_groups: int = 0
    total_duplicates: int = 0


class DedupCheckRequest(BaseModel):
    model: str
    values: dict[str, Any]


class DedupCheckResponse(BaseModel):
    has_duplicates: bool = False
    matches: list[dict[str, Any]] = []


class DedupMergeRequest(BaseModel):
    master_record_id: int
    merged_by: str = "admin"


class DedupMergeResponse(BaseModel):
    merged: bool = True
    group_id: int
    master_record_id: int
    merged_record_ids: list[int] = []


# ---------------------------------------------------------------------------
# Customer Credit Management (1.6)
# ---------------------------------------------------------------------------

class CreditScoreResponse(BaseModel):
    customer_id: int
    customer_name: str = ""
    credit_score: float = 0.0
    risk_level: str = "normal"
    credit_limit: float = 0.0
    current_exposure: float = 0.0
    overdue_amount: float = 0.0
    hold_active: bool = False
    hold_reason: str | None = None
    breakdown: dict[str, float] = {}

    model_config = {"from_attributes": True}


class CreditCheckRequest(BaseModel):
    customer_id: int
    order_amount: float = 0.0


class CreditCheckResponse(BaseModel):
    allowed: bool = True
    reason: str = ""
    credit_score: float | None = None
    risk_level: str | None = None
    current_exposure: float | None = None
    credit_limit: float | None = None
    remaining_credit: float | None = None
    over_limit_by: float | None = None


class CreditHoldReleaseResponse(BaseModel):
    releases: list[dict[str, Any]] = []
    total_checked: int = 0


class CreditBatchResponse(BaseModel):
    total_customers: int = 0
    updated: int = 0
    errors: int = 0


# ---------------------------------------------------------------------------
# Smart Invoice Processing / IDP (1.4)
# ---------------------------------------------------------------------------

class DocumentProcessResponse(BaseModel):
    job_id: int
    status: str = "processing"


class LineItemExtraction(BaseModel):
    description: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    product_code: str = ""


class DocumentExtractionResult(BaseModel):
    vendor: str = ""
    vendor_vat: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    due_date: str = ""
    currency: str = ""
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    po_reference: str = ""
    line_items: list[LineItemExtraction] = []
    payment_terms: str = ""
    notes: str = ""


class DocumentJobResponse(BaseModel):
    job_id: int
    file_name: str = ""
    document_type: str = ""
    status: str = "queued"
    extraction: DocumentExtractionResult | None = None
    confidence: float = 0.0
    field_confidences: dict[str, float] = {}
    matched_vendor_id: int | None = None
    matched_vendor_name: str = ""
    matched_po_id: int | None = None
    po_validation: dict[str, Any] | None = None
    odoo_record_created: int | None = None
    error_message: str | None = None
    processing_time_ms: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentCorrectionRequest(BaseModel):
    field_name: str
    corrected_value: str


class DocumentCorrectionResponse(BaseModel):
    correction_saved: bool = True
    job_id: int
    field_name: str
    original_value: str | None = None
    corrected_value: str = ""


# ---------------------------------------------------------------------------
# Proactive AI Daily Digest (1.11)
# ---------------------------------------------------------------------------

class DigestMetric(BaseModel):
    name: str
    value: Any
    change: float | None = None
    change_label: str = ""


class DigestAttentionItem(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    odoo_model: str = ""
    odoo_record_id: int | None = None
    link: str = ""


class DigestAnomaly(BaseModel):
    description: str
    severity: str = "medium"
    source: str = ""


class DigestContent(BaseModel):
    headline: str = ""
    key_metrics: list[DigestMetric] = []
    attention_items: list[DigestAttentionItem] = []
    anomalies: list[DigestAnomaly] = []
    summary: str = ""


class DigestResponse(BaseModel):
    digest_id: int | None = None
    digest_date: str = ""
    role: str = ""
    content: DigestContent
    channels_sent: list[str] = []
    delivered: bool = False
    generated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DigestSendRequest(BaseModel):
    role: str
    channel: str = "email"
    recipient: str = ""


class DigestSendResponse(BaseModel):
    sent: bool = True
    channel: str = ""
    role: str = ""


class DigestConfigRequest(BaseModel):
    role: str
    channels: list[str] = ["email"]
    send_time: str = "07:00"
    enabled: bool = True


class DigestConfigResponse(BaseModel):
    updated: bool = True
    role: str = ""
    channels: list[str] = []
    send_time: str = "07:00"


# ---------------------------------------------------------------------------
# Cash Flow Forecasting (1.8)
# ---------------------------------------------------------------------------

class ForecastDataPoint(BaseModel):
    date: str
    balance: float = 0.0
    low: float = 0.0
    high: float = 0.0
    ar_expected: float = 0.0
    ap_expected: float = 0.0
    pipeline_expected: float = 0.0
    recurring_expected: float = 0.0


class ForecastSummary(BaseModel):
    total_ar: float = 0.0
    total_ap: float = 0.0
    total_pipeline: float = 0.0
    total_recurring: float = 0.0
    net_position: float = 0.0


class CashFlowForecastResponse(BaseModel):
    generated_at: datetime | None = None
    horizon_days: int = 90
    current_balance: float = 0.0
    forecasts: list[ForecastDataPoint] = []
    ar_summary: ForecastSummary = ForecastSummary()
    ap_summary: ForecastSummary = ForecastSummary()
    cash_gap_dates: list[str] = []
    model_version: str = "v1.0"


class ScenarioRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Descriptive scenario name")
    adjustments: dict[str, Any] = Field(
        default_factory=dict,
        description="Adjustments: delay_customer_{id}, remove_deal_{id}, adjust_expense_{category}",
    )
    description: str = ""


class ScenarioResponse(BaseModel):
    scenario_id: int
    name: str
    forecasts: list[ForecastDataPoint] = []
    impact: dict[str, Any] = {}
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ForecastAccuracyResponse(BaseModel):
    last_30_days: dict[str, float] = {}
    last_60_days: dict[str, float] = {}
    last_90_days: dict[str, float] = {}
    total_comparisons: int = 0


# ---------------------------------------------------------------------------
# Natural Language Report Builder (1.7)
# ---------------------------------------------------------------------------

class ReportGenerateRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural language report request")
    format: str = Field(default="table", pattern=r"^(table|excel|pdf)$")


class ReportColumn(BaseModel):
    name: str
    label: str = ""
    type: str = "string"


class ReportGenerateResponse(BaseModel):
    job_id: int
    status: str = "generating"


class ReportJobResponse(BaseModel):
    job_id: int
    status: str = "pending"
    request_text: str = ""
    format: str = "table"
    parsed_query: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReportScheduleRequest(BaseModel):
    query: str = Field(..., min_length=3)
    cron: str = Field(..., description="Cron expression, e.g. '0 8 * * MON'")
    format: str = Field(default="pdf", pattern=r"^(table|excel|pdf)$")
    deliver_via: str = "email"
    recipient: str = ""


class ReportScheduleResponse(BaseModel):
    job_id: int
    schedule: str = ""
    next_run: str = ""


# ---------------------------------------------------------------------------
# Role-Based AI Dashboards (1.10)
# ---------------------------------------------------------------------------

class AgingBucket(BaseModel):
    bucket: str
    amount: float = 0.0
    count: int = 0


class PLSummary(BaseModel):
    total_revenue: float = 0.0
    total_expenses: float = 0.0
    net_income: float = 0.0
    period: str = ""


class CloseStatusSummary(BaseModel):
    period: str = ""
    status: str = "not_started"
    progress_pct: float = 0.0
    steps_total: int = 0
    steps_completed: int = 0


class CFODashboardResponse(BaseModel):
    cash_position: float = 0.0
    total_ar: float = 0.0
    total_ap: float = 0.0
    ar_aging: list[AgingBucket] = []
    ap_aging: list[AgingBucket] = []
    cash_forecast: list[ForecastDataPoint] = []
    pl_summary: PLSummary = PLSummary()
    close_status: CloseStatusSummary = CloseStatusSummary()
    pending_approvals: int = 0
    anomalies: list[DigestAnomaly] = []
    generated_at: datetime | None = None


class PipelineStage(BaseModel):
    stage: str
    count: int = 0
    value: float = 0.0


class AtRiskDeal(BaseModel):
    lead_id: int
    name: str = ""
    value: float = 0.0
    probability: float = 0.0
    days_stale: int = 0
    stage: str = ""


class SalesDashboardResponse(BaseModel):
    pipeline_value: float = 0.0
    pipeline_stages: list[PipelineStage] = []
    win_rate: float = 0.0
    deals_closing_this_month: int = 0
    at_risk_deals: list[AtRiskDeal] = []
    conversion_funnel: list[PipelineStage] = []
    revenue_this_month: float = 0.0
    quota_target: float = 0.0
    quota_pct: float = 0.0
    recent_automations: int = 0
    generated_at: datetime | None = None


class StockAlert(BaseModel):
    product_id: int
    product_name: str = ""
    qty_available: float = 0.0
    reorder_point: float = 0.0
    status: str = "ok"


class ShipmentSummary(BaseModel):
    incoming_count: int = 0
    incoming_ready: int = 0
    outgoing_count: int = 0
    outgoing_ready: int = 0


class WarehouseDashboardResponse(BaseModel):
    total_products: int = 0
    below_reorder: int = 0
    stock_alerts: list[StockAlert] = []
    shipments: ShipmentSummary = ShipmentSummary()
    recent_automations: int = 0
    generated_at: datetime | None = None


class WebSocketMessage(BaseModel):
    type: str
    data: dict[str, Any] = {}
    timestamp: datetime | None = None
    role: str | None = None
