"""
Cross-app intelligence: correlates data across all Odoo modules
to surface insights, predict trends, and suggest proactive actions.
"""

import json
from datetime import date

import structlog

from app.odoo_client import get_odoo_client
from app.claude_client import get_claude_client
from app.config import get_settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert ERP Intelligence AI that analyzes data across all
business modules (Accounting, CRM, Sales, Purchase, Inventory, HR, Project, etc.)
to find cross-functional insights, correlations, and proactive recommendations.

Your role is to be a strategic advisor — surfacing things humans would miss
because they only see their own module. Think holistically about the business."""

INSIGHT_TOOLS = [
    {
        "name": "generate_insights",
        "description": "Generate cross-app business insights and recommendations",
        "input_schema": {
            "type": "object",
            "properties": {
                "insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "category": {
                                "type": "string",
                                "enum": ["opportunity", "risk", "efficiency", "trend", "anomaly"],
                            },
                            "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                            "description": {"type": "string"},
                            "affected_modules": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "recommended_action": {"type": "string"},
                            "estimated_impact": {"type": "string"},
                        },
                    },
                },
                "executive_summary": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["insights", "executive_summary", "confidence"],
        },
    }
]


class CrossAppIntelligence:
    """Runs periodic cross-module analysis to surface insights."""

    def __init__(self):
        self.settings = get_settings()

    @property
    def odoo(self):
        return get_odoo_client()

    @property
    def claude(self):
        return get_claude_client()

    def run_full_analysis(self) -> dict:
        """Gather data from all modules and run cross-app intelligence analysis."""
        data = self._gather_cross_app_data()
        return self._analyze(data)

    def _gather_cross_app_data(self) -> dict:
        """Fetch summary data from all essential modules."""
        data = {}

        try:
            data["sales_pipeline"] = self.odoo.search_read(
                "sale.order",
                [("state", "in", ["draft", "sent", "sale"])],
                fields=["name", "partner_id", "amount_total", "state", "date_order"],
                limit=30,
            )
        except Exception:
            data["sales_pipeline"] = []

        try:
            data["crm_leads"] = self.odoo.search_read(
                "crm.lead",
                [("active", "=", True), ("type", "=", "lead")],
                fields=["name", "expected_revenue", "probability", "stage_id", "create_date"],
                limit=30,
            )
        except Exception:
            data["crm_leads"] = []

        try:
            data["open_invoices"] = self.odoo.search_read(
                "account.move",
                [("state", "=", "posted"), ("payment_state", "in", ["not_paid", "partial"])],
                fields=["name", "partner_id", "amount_residual", "invoice_date_due", "move_type"],
                limit=30,
            )
        except Exception:
            data["open_invoices"] = []

        try:
            data["low_stock"] = self.odoo.search_read(
                "product.product",
                [("type", "=", "product"), ("qty_available", "<", 10)],
                fields=["name", "qty_available", "virtual_available", "default_code"],
                limit=20,
            )
        except Exception:
            data["low_stock"] = []

        try:
            data["open_purchase_orders"] = self.odoo.search_read(
                "purchase.order",
                [("state", "in", ["draft", "sent"])],
                fields=["name", "partner_id", "amount_total", "date_planned"],
                limit=20,
            )
        except Exception:
            data["open_purchase_orders"] = []

        try:
            data["overdue_tasks"] = self.odoo.search_read(
                "project.task",
                [("date_deadline", "<", date.today().isoformat()), ("stage_id.fold", "=", False)],
                fields=["name", "project_id", "user_ids", "date_deadline"],
                limit=20,
            )
        except Exception:
            data["overdue_tasks"] = []

        try:
            data["pending_leaves"] = self.odoo.search_read(
                "hr.leave",
                [("state", "=", "confirm")],
                fields=["employee_id", "date_from", "date_to", "number_of_days"],
                limit=10,
            )
        except Exception:
            data["pending_leaves"] = []

        return data

    def _analyze(self, data: dict) -> dict:
        """Send all cross-app data to Claude for holistic analysis."""
        user_msg = f"""Analyze this cross-functional business data and provide strategic insights:

## Sales Pipeline
{json.dumps(data.get('sales_pipeline', [])[:15], indent=2, default=str)}

## CRM Leads
{json.dumps(data.get('crm_leads', [])[:15], indent=2, default=str)}

## Open Invoices (unpaid)
{json.dumps(data.get('open_invoices', [])[:15], indent=2, default=str)}

## Low Stock Products
{json.dumps(data.get('low_stock', [])[:15], indent=2, default=str)}

## Open Purchase Orders
{json.dumps(data.get('open_purchase_orders', [])[:10], indent=2, default=str)}

## Overdue Project Tasks
{json.dumps(data.get('overdue_tasks', [])[:10], indent=2, default=str)}

## Pending Leave Requests
{json.dumps(data.get('pending_leaves', [])[:10], indent=2, default=str)}

Look for cross-module patterns:
- Sales up but inventory low? Suggest purchasing action.
- Many overdue invoices from same partner? Flag credit risk.
- Key team members on leave when deadlines approach? Warn about capacity.
- Sales pipeline strong but project resources stretched? Hiring signal.
- Seasonal patterns across modules.
- Cash flow implications of current operations."""

        result = self.claude.analyze(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_msg,
            tools=INSIGHT_TOOLS,
        )

        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]

        return {
            "insights": [],
            "executive_summary": result.get("text", "Analysis completed"),
            "confidence": 0.5,
        }
