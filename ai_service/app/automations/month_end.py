"""
Month-End Closing Assistant — AI-powered closing checklist.

Scans Odoo for: unreconciled bank items, stale drafts, unbilled deliveries,
missing recurring bills, unposted depreciation, tax validation issues,
uninvoiced timesheets, and inter-company balances.
"""

import json
from datetime import datetime, date, timedelta
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

CLOSING_STEPS = [
    {"name": "reconcile_bank", "order": 1, "label": "Reconcile Bank Transactions"},
    {"name": "review_stale_drafts", "order": 2, "label": "Review Stale Draft Entries"},
    {"name": "unbilled_deliveries", "order": 3, "label": "Accrue Unbilled Deliveries"},
    {"name": "missing_vendor_bills", "order": 4, "label": "Check Missing Vendor Bills"},
    {"name": "uninvoiced_revenue", "order": 5, "label": "Invoice Unbilled Revenue"},
    {"name": "depreciation_entries", "order": 6, "label": "Post Depreciation Entries"},
    {"name": "tax_validation", "order": 7, "label": "Validate Tax Entries"},
    {"name": "intercompany_balances", "order": 8, "label": "Review Inter-Company Balances"},
    {"name": "review_adjustments", "order": 9, "label": "Review Manual Adjustments"},
    {"name": "final_review", "order": 10, "label": "Final P&L / Balance Sheet Review"},
]

CLOSING_ANALYSIS_PROMPT = """You are an expert accounting controller AI assistant.
Analyze the month-end closing data and provide a clear summary.
Identify risks, highlight items needing attention, and suggest priorities.
Be specific about amounts and counts. Use professional accounting language."""

CLOSING_ANALYSIS_TOOLS = [
    {
        "name": "closing_analysis",
        "description": "Provide a structured month-end closing analysis with issues and recommendations",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Executive summary of closing readiness (2-3 sentences)",
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Overall risk level for the close",
                },
                "priority_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top 3-5 actions the controller should take first",
                },
                "estimated_completion_hours": {
                    "type": "number",
                    "description": "Estimated hours to complete the close based on findings",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in the analysis (0.0-1.0)",
                },
            },
            "required": ["summary", "risk_level", "priority_actions", "estimated_completion_hours", "confidence"],
        },
    }
]


class MonthEndClosingAutomation(BaseAutomation):
    automation_type = "month_end"
    watched_models = ["account.move"]

    def get_period_dates(self, period: str) -> tuple[str, str]:
        """Convert YYYY-MM to first and last day of month."""
        year, month = int(period[:4]), int(period[5:7])
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        return first_day.isoformat(), last_day.isoformat()

    def run_full_scan(self, period: str) -> dict[str, Any]:
        """Execute all closing checks against Odoo and return step results."""
        date_from, date_to = self.get_period_dates(period)
        results: dict[str, Any] = {}

        scan_methods = {
            "reconcile_bank": self._scan_unreconciled_bank,
            "review_stale_drafts": self._scan_stale_drafts,
            "unbilled_deliveries": self._scan_unbilled_deliveries,
            "missing_vendor_bills": self._scan_missing_vendor_bills,
            "uninvoiced_revenue": self._scan_uninvoiced_revenue,
            "depreciation_entries": self._scan_depreciation,
            "tax_validation": self._scan_tax_issues,
            "intercompany_balances": self._scan_intercompany,
            "review_adjustments": self._scan_adjustments,
            "final_review": self._scan_final_review,
        }

        for step_name, scan_fn in scan_methods.items():
            try:
                results[step_name] = scan_fn(date_from, date_to)
            except Exception as exc:
                logger.error("closing_scan_step_failed", step=step_name, error=str(exc))
                results[step_name] = {
                    "items_found": 0,
                    "details": [],
                    "error": str(exc),
                }

        return results

    def generate_ai_summary(self, period: str, scan_results: dict) -> dict[str, Any]:
        """Ask Claude to analyze the scan results and produce a closing summary."""
        step_summary_lines = []
        for step in CLOSING_STEPS:
            result = scan_results.get(step["name"], {})
            count = result.get("items_found", 0)
            step_summary_lines.append(f"- {step['label']}: {count} items found")

        user_msg = f"""Analyze the month-end closing scan for period {period}:

Scan Results:
{chr(10).join(step_summary_lines)}

Detailed findings:
{json.dumps(scan_results, indent=2, default=str)}

Provide an executive summary, risk assessment, and priority actions."""

        try:
            result = self.analyze_with_tools(
                CLOSING_ANALYSIS_PROMPT, user_msg, CLOSING_ANALYSIS_TOOLS
            )
            if result.get("tool_calls"):
                return result["tool_calls"][0]["input"]
        except Exception as exc:
            logger.error("closing_ai_summary_failed", error=str(exc))

        total_issues = sum(
            r.get("items_found", 0) for r in scan_results.values()
        )
        return {
            "summary": f"Closing scan found {total_issues} items across all steps. Manual review recommended.",
            "risk_level": "high" if total_issues > 20 else "medium" if total_issues > 5 else "low",
            "priority_actions": ["Review scan results manually"],
            "estimated_completion_hours": max(1, total_issues * 0.25),
            "confidence": 0.5,
        }

    # ------------------------------------------------------------------
    # Individual scan methods — each queries Odoo and returns findings
    # ------------------------------------------------------------------

    def _scan_unreconciled_bank(self, date_from: str, date_to: str) -> dict:
        lines = self.fetch_related_records(
            "account.bank.statement.line",
            [
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("is_reconciled", "=", False),
            ],
            fields=["date", "payment_ref", "amount", "journal_id", "partner_id"],
            limit=200,
        )
        total_amount = sum(abs(l.get("amount", 0)) for l in lines)
        return {
            "items_found": len(lines),
            "total_amount": total_amount,
            "details": lines[:50],
        }

    def _scan_stale_drafts(self, date_from: str, date_to: str) -> dict:
        cutoff = (datetime.strptime(date_to, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        drafts = self.fetch_related_records(
            "account.move",
            [
                ("state", "=", "draft"),
                ("date", "<=", cutoff),
                ("date", ">=", date_from),
            ],
            fields=["name", "date", "amount_total", "partner_id", "move_type"],
            limit=100,
        )
        total_amount = sum(abs(d.get("amount_total", 0)) for d in drafts)
        return {
            "items_found": len(drafts),
            "total_amount": total_amount,
            "details": drafts[:50],
        }

    def _scan_unbilled_deliveries(self, date_from: str, date_to: str) -> dict:
        pickings = self.fetch_related_records(
            "stock.picking",
            [
                ("date_done", ">=", date_from),
                ("date_done", "<=", date_to),
                ("state", "=", "done"),
                ("picking_type_code", "=", "outgoing"),
            ],
            fields=["name", "date_done", "partner_id", "sale_id", "origin"],
            limit=100,
        )
        unbilled = []
        for picking in pickings:
            sale_id = picking.get("sale_id")
            if sale_id and isinstance(sale_id, (list, tuple)):
                sale_id = sale_id[0]
            if sale_id:
                order = self.fetch_record_context(
                    "sale.order", sale_id, ["invoice_status"]
                )
                if order and order.get("invoice_status") != "invoiced":
                    unbilled.append(picking)
        return {
            "items_found": len(unbilled),
            "details": unbilled[:50],
        }

    def _scan_missing_vendor_bills(self, date_from: str, date_to: str) -> dict:
        receipts = self.fetch_related_records(
            "stock.picking",
            [
                ("date_done", ">=", date_from),
                ("date_done", "<=", date_to),
                ("state", "=", "done"),
                ("picking_type_code", "=", "incoming"),
            ],
            fields=["name", "date_done", "partner_id", "origin"],
            limit=100,
        )
        po_ids_seen: set[int] = set()
        missing = []
        for receipt in receipts:
            origin = receipt.get("origin", "")
            if not origin:
                continue
            pos = self.fetch_related_records(
                "purchase.order",
                [("name", "=", origin)],
                fields=["id", "name", "invoice_status"],
                limit=1,
            )
            for po in pos:
                if po["id"] not in po_ids_seen and po.get("invoice_status") != "invoiced":
                    po_ids_seen.add(po["id"])
                    missing.append(po)
        return {
            "items_found": len(missing),
            "details": missing[:50],
        }

    def _scan_uninvoiced_revenue(self, date_from: str, date_to: str) -> dict:
        orders = self.fetch_related_records(
            "sale.order",
            [
                ("date_order", ">=", date_from),
                ("date_order", "<=", date_to),
                ("state", "=", "sale"),
                ("invoice_status", "=", "to invoice"),
            ],
            fields=["name", "date_order", "amount_total", "partner_id"],
            limit=100,
        )
        total = sum(o.get("amount_total", 0) for o in orders)
        return {
            "items_found": len(orders),
            "total_amount": total,
            "details": orders[:50],
        }

    def _scan_depreciation(self, date_from: str, date_to: str) -> dict:
        unposted = self.fetch_related_records(
            "account.move",
            [
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("state", "=", "draft"),
                ("move_type", "=", "entry"),
            ],
            fields=["name", "date", "amount_total", "ref"],
            limit=50,
        )
        depreciation_entries = [
            e for e in unposted
            if "depreciation" in (e.get("ref") or "").lower()
            or "depreciation" in (e.get("name") or "").lower()
        ]
        return {
            "items_found": len(depreciation_entries),
            "details": depreciation_entries,
        }

    def _scan_tax_issues(self, date_from: str, date_to: str) -> dict:
        posted_moves = self.fetch_related_records(
            "account.move",
            [
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("state", "=", "posted"),
                ("move_type", "in", ["out_invoice", "in_invoice"]),
            ],
            fields=["name", "amount_tax", "amount_total", "fiscal_position_id"],
            limit=200,
        )
        no_tax = [m for m in posted_moves if not m.get("amount_tax")]
        return {
            "items_found": len(no_tax),
            "total_invoices_checked": len(posted_moves),
            "details": no_tax[:50],
        }

    def _scan_intercompany(self, date_from: str, date_to: str) -> dict:
        # Placeholder — only relevant for multi-company setups
        return {"items_found": 0, "details": [], "note": "Single-company mode"}

    def _scan_adjustments(self, date_from: str, date_to: str) -> dict:
        adjustments = self.fetch_related_records(
            "account.move",
            [
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("state", "=", "posted"),
                ("move_type", "=", "entry"),
            ],
            fields=["name", "date", "amount_total", "ref", "narration"],
            limit=100,
        )
        return {
            "items_found": len(adjustments),
            "details": adjustments[:50],
        }

    def _scan_final_review(self, date_from: str, date_to: str) -> dict:
        return {
            "items_found": 0,
            "details": [],
            "note": "Requires manual P&L and Balance Sheet review after all other steps are complete",
        }

    # ------------------------------------------------------------------
    # Webhook handlers (optional — auto-trigger on accounting events)
    # ------------------------------------------------------------------

    def on_write_account_move(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        return AutomationResult(
            success=True,
            action="month_end_event_logged",
            model=model,
            record_id=record_id,
            reasoning="Account move write noted for month-end tracking",
        )
