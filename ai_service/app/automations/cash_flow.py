"""
Cash Flow Forecasting — 30/60/90-day cash position predictions.

Pulls AR aging, AP commitments, sales pipeline (weighted by probability),
and recurring expenses from Odoo. Generates confidence bands, scenario
planning, and accuracy tracking.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

MODEL_VERSION = "v1.0-statistical"

CONFIDENCE_BAND_WIDTH = 0.15

FORECAST_PROMPT = """You are a treasury intelligence analyst for an ERP system.
Analyze cash flow data including AR aging, AP commitments, sales pipeline,
and recurring expenses. Provide a cash flow assessment with risk areas,
recommendations, and confidence in the forecast accuracy."""

FORECAST_TOOLS = [
    {
        "name": "cash_flow_assessment",
        "description": "Provide cash flow forecast assessment",
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "moderate", "high", "critical"],
                },
                "cash_gap_warning": {
                    "type": "boolean",
                    "description": "Whether a cash gap is predicted",
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in forecast 0-1",
                },
                "summary": {
                    "type": "string",
                },
            },
            "required": ["risk_level", "cash_gap_warning", "recommendations", "confidence", "summary"],
        },
    }
]


class CashFlowForecastingAutomation(BaseAutomation):
    """Cash flow forecasting with scenario planning and accuracy tracking."""

    automation_type = "forecasting"
    watched_models = ["account.move", "account.payment"]

    def generate_forecast(self, horizon_days: int = 90) -> dict[str, Any]:
        """
        Generate a full cash flow forecast for the given horizon.
        Combines AR aging, AP commitments, pipeline, and recurring expenses.
        """
        today = date.today()

        current_balance = self._get_current_balance()
        ar_data = self._collect_ar_aging()
        ap_data = self._collect_ap_commitments()
        pipeline_data = self._collect_pipeline_weighted()
        recurring_data = self._collect_recurring_expenses()

        forecasts = []
        running_balance = current_balance

        for day_offset in range(1, horizon_days + 1):
            target = today + timedelta(days=day_offset)
            target_str = target.isoformat()

            ar_day = self._sum_for_date(ar_data, target)
            ap_day = self._sum_for_date(ap_data, target)
            pipeline_day = self._sum_for_date(pipeline_data, target)
            recurring_day = self._recurring_for_date(recurring_data, target)

            net_change = ar_day + pipeline_day - ap_day - recurring_day
            running_balance += net_change

            uncertainty = CONFIDENCE_BAND_WIDTH * abs(running_balance) * (day_offset / horizon_days)
            low = running_balance - uncertainty
            high = running_balance + uncertainty

            forecasts.append({
                "date": target_str,
                "balance": round(running_balance, 2),
                "low": round(low, 2),
                "high": round(high, 2),
                "ar_expected": round(ar_day, 2),
                "ap_expected": round(ap_day, 2),
                "pipeline_expected": round(pipeline_day, 2),
                "recurring_expected": round(recurring_day, 2),
            })

        cash_gap_dates = [f["date"] for f in forecasts if f["balance"] < 0]

        ar_summary = {
            "total_ar": round(sum(item["amount"] for item in ar_data), 2),
            "total_ap": 0.0,
            "total_pipeline": 0.0,
            "total_recurring": 0.0,
            "net_position": 0.0,
        }
        ap_summary = {
            "total_ar": 0.0,
            "total_ap": round(sum(item["amount"] for item in ap_data), 2),
            "total_pipeline": round(sum(item["amount"] for item in pipeline_data), 2),
            "total_recurring": round(sum(item["amount"] for item in recurring_data), 2),
            "net_position": 0.0,
        }
        ar_summary["net_position"] = ar_summary["total_ar"]
        ap_summary["net_position"] = -(ap_summary["total_ap"] + ap_summary["total_recurring"])

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "horizon_days": horizon_days,
            "current_balance": round(current_balance, 2),
            "forecasts": forecasts,
            "ar_summary": ar_summary,
            "ap_summary": ap_summary,
            "cash_gap_dates": cash_gap_dates,
            "model_version": MODEL_VERSION,
        }

    def run_scenario(
        self,
        name: str,
        adjustments: dict[str, Any],
        description: str = "",
        horizon_days: int = 90,
    ) -> dict[str, Any]:
        """
        Run a what-if scenario by adjusting the forecast inputs.

        Supported adjustments:
        - delay_customer_{id}: int (days to delay payment)
        - remove_deal_{id}: bool (remove deal from pipeline)
        - adjust_expense_{category}: float (multiplier for expense category)
        - reduce_ar_by: float (percentage reduction in expected AR)
        - increase_ap_by: float (percentage increase in expected AP)
        """
        today = date.today()
        current_balance = self._get_current_balance()
        ar_data = self._collect_ar_aging()
        ap_data = self._collect_ap_commitments()
        pipeline_data = self._collect_pipeline_weighted()
        recurring_data = self._collect_recurring_expenses()

        ar_data = self._apply_ar_adjustments(ar_data, adjustments)
        pipeline_data = self._apply_pipeline_adjustments(pipeline_data, adjustments)
        ap_data = self._apply_ap_adjustments(ap_data, adjustments)
        recurring_data = self._apply_recurring_adjustments(recurring_data, adjustments)

        forecasts = []
        running_balance = current_balance

        for day_offset in range(1, horizon_days + 1):
            target = today + timedelta(days=day_offset)
            target_str = target.isoformat()

            ar_day = self._sum_for_date(ar_data, target)
            ap_day = self._sum_for_date(ap_data, target)
            pipeline_day = self._sum_for_date(pipeline_data, target)
            recurring_day = self._recurring_for_date(recurring_data, target)

            net_change = ar_day + pipeline_day - ap_day - recurring_day
            running_balance += net_change

            uncertainty = CONFIDENCE_BAND_WIDTH * abs(running_balance) * (day_offset / horizon_days)

            forecasts.append({
                "date": target_str,
                "balance": round(running_balance, 2),
                "low": round(running_balance - uncertainty, 2),
                "high": round(running_balance + uncertainty, 2),
                "ar_expected": round(ar_day, 2),
                "ap_expected": round(ap_day, 2),
                "pipeline_expected": round(pipeline_day, 2),
                "recurring_expected": round(recurring_day, 2),
            })

        cash_gap_dates = [f["date"] for f in forecasts if f["balance"] < 0]
        base_forecast = self.generate_forecast(horizon_days)
        base_end = base_forecast["forecasts"][-1]["balance"] if base_forecast["forecasts"] else current_balance
        scenario_end = forecasts[-1]["balance"] if forecasts else current_balance

        impact = {
            "cash_gap_dates": cash_gap_dates,
            "end_balance_change": round(scenario_end - base_end, 2),
            "worst_balance": round(min(f["balance"] for f in forecasts), 2) if forecasts else 0,
            "worst_date": min(forecasts, key=lambda f: f["balance"])["date"] if forecasts else "",
            "has_cash_gap": len(cash_gap_dates) > 0,
        }
        if cash_gap_dates:
            impact["cash_gap_date"] = cash_gap_dates[0]

        return {
            "name": name,
            "description": description,
            "adjustments": adjustments,
            "forecasts": forecasts,
            "impact": impact,
        }

    def check_accuracy(self, lookback_days: int = 90) -> dict[str, Any]:
        """
        Compare past forecasts with actual balances to compute accuracy metrics.
        Returns MAE and MAPE for 30/60/90-day windows.
        """
        from app.models.audit import ForecastAccuracyLog, get_db_session

        result = {
            "last_30_days": {"mae": 0.0, "mape": 0.0},
            "last_60_days": {"mae": 0.0, "mape": 0.0},
            "last_90_days": {"mae": 0.0, "mape": 0.0},
            "total_comparisons": 0,
        }

        try:
            with get_db_session() as session:
                cutoff = date.today() - timedelta(days=lookback_days)
                logs = (
                    session.query(ForecastAccuracyLog)
                    .filter(ForecastAccuracyLog.target_date >= cutoff)
                    .all()
                )

                if not logs:
                    return result

                result["total_comparisons"] = len(logs)

                for window_name, window_days in [("last_30_days", 30), ("last_60_days", 60), ("last_90_days", 90)]:
                    window_cutoff = date.today() - timedelta(days=window_days)
                    window_logs = [lg for lg in logs if lg.target_date >= window_cutoff]
                    if window_logs:
                        errors = []
                        pct_errors = []
                        for lg in window_logs:
                            pred = float(lg.predicted_balance or 0)
                            actual = float(lg.actual_balance or 0)
                            errors.append(abs(pred - actual))
                            if actual != 0:
                                pct_errors.append(abs(pred - actual) / abs(actual) * 100)
                        result[window_name]["mae"] = round(float(np.mean(errors)), 2) if errors else 0.0
                        result[window_name]["mape"] = round(float(np.mean(pct_errors)), 2) if pct_errors else 0.0

        except Exception as exc:
            logger.error("forecast_accuracy_check_failed", error=str(exc))

        return result

    def record_actual_balance(self, target_date: date, actual_balance: float):
        """Record actual balance for a date to enable accuracy tracking."""
        from app.models.audit import CashForecast, ForecastAccuracyLog, get_db_session

        try:
            with get_db_session() as session:
                forecasts = (
                    session.query(CashForecast)
                    .filter(CashForecast.target_date == target_date)
                    .all()
                )

                for fc in forecasts:
                    predicted = float(fc.predicted_balance)
                    error_pct = (
                        abs(predicted - actual_balance) / abs(actual_balance) * 100
                        if actual_balance != 0
                        else 0.0
                    )
                    accuracy_log = ForecastAccuracyLog(
                        forecast_id=fc.id,
                        target_date=target_date,
                        predicted_balance=Decimal(str(predicted)),
                        actual_balance=Decimal(str(actual_balance)),
                        error_pct=Decimal(str(round(error_pct, 4))),
                    )
                    session.add(accuracy_log)

        except Exception as exc:
            logger.error("record_actual_balance_failed", error=str(exc))

    def persist_forecast(self, forecast_data: dict[str, Any]):
        """Save forecast data points to the database."""
        from app.models.audit import CashForecast, get_db_session

        try:
            with get_db_session() as session:
                forecast_date = date.today()
                for point in forecast_data.get("forecasts", []):
                    fc = CashForecast(
                        forecast_date=forecast_date,
                        target_date=date.fromisoformat(point["date"]),
                        predicted_balance=Decimal(str(point["balance"])),
                        confidence_low=Decimal(str(point["low"])),
                        confidence_high=Decimal(str(point["high"])),
                        ar_expected=Decimal(str(point["ar_expected"])),
                        ap_expected=Decimal(str(point["ap_expected"])),
                        pipeline_expected=Decimal(str(point["pipeline_expected"])),
                        recurring_expected=Decimal(str(point["recurring_expected"])),
                        model_version=MODEL_VERSION,
                    )
                    session.add(fc)

        except Exception as exc:
            logger.error("persist_forecast_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Data collection from Odoo
    # ------------------------------------------------------------------

    def _get_current_balance(self) -> float:
        """Fetch current bank balance from Odoo bank journals."""
        try:
            journals = self.fetch_related_records(
                "account.journal",
                [("type", "=", "bank")],
                fields=["id", "name", "default_account_id"],
                limit=20,
            )
            if not journals:
                return 0.0

            total = 0.0
            for journal in journals:
                account_id = journal.get("default_account_id")
                if isinstance(account_id, (list, tuple)):
                    account_id = account_id[0]
                if not account_id:
                    continue

                lines = self.fetch_related_records(
                    "account.move.line",
                    [
                        ("account_id", "=", account_id),
                        ("parent_state", "=", "posted"),
                    ],
                    fields=["balance"],
                    limit=5000,
                )
                total += sum(float(l.get("balance", 0)) for l in lines)

            return round(total, 2)
        except Exception as exc:
            logger.warning("current_balance_fetch_failed", error=str(exc))
            return 0.0

    def _collect_ar_aging(self) -> list[dict[str, Any]]:
        """Collect accounts receivable aging — open invoices with due dates."""
        try:
            invoices = self.fetch_related_records(
                "account.move",
                [
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    ("payment_state", "in", ["not_paid", "partial"]),
                ],
                fields=["partner_id", "amount_residual", "invoice_date_due", "name"],
                limit=500,
            )
            result = []
            for inv in invoices:
                due = inv.get("invoice_date_due")
                if not due:
                    due = (date.today() + timedelta(days=30)).isoformat()

                partner_id = inv.get("partner_id")
                if isinstance(partner_id, (list, tuple)):
                    partner_id = partner_id[0]

                result.append({
                    "type": "ar",
                    "amount": float(inv.get("amount_residual", 0)),
                    "due_date": str(due),
                    "partner_id": partner_id,
                    "reference": inv.get("name", ""),
                })
            return result
        except Exception as exc:
            logger.warning("ar_aging_fetch_failed", error=str(exc))
            return []

    def _collect_ap_commitments(self) -> list[dict[str, Any]]:
        """Collect accounts payable — open vendor bills with due dates."""
        try:
            bills = self.fetch_related_records(
                "account.move",
                [
                    ("move_type", "=", "in_invoice"),
                    ("state", "=", "posted"),
                    ("payment_state", "in", ["not_paid", "partial"]),
                ],
                fields=["partner_id", "amount_residual", "invoice_date_due", "name"],
                limit=500,
            )
            result = []
            for bill in bills:
                due = bill.get("invoice_date_due")
                if not due:
                    due = (date.today() + timedelta(days=30)).isoformat()

                partner_id = bill.get("partner_id")
                if isinstance(partner_id, (list, tuple)):
                    partner_id = partner_id[0]

                result.append({
                    "type": "ap",
                    "amount": float(bill.get("amount_residual", 0)),
                    "due_date": str(due),
                    "partner_id": partner_id,
                    "reference": bill.get("name", ""),
                })
            return result
        except Exception as exc:
            logger.warning("ap_commitments_fetch_failed", error=str(exc))
            return []

    def _collect_pipeline_weighted(self) -> list[dict[str, Any]]:
        """Collect sales pipeline weighted by probability."""
        try:
            deals = self.fetch_related_records(
                "crm.lead",
                [
                    ("type", "=", "opportunity"),
                    ("active", "=", True),
                    ("probability", ">", 0),
                ],
                fields=["name", "expected_revenue", "probability", "date_deadline", "partner_id"],
                limit=200,
            )
            result = []
            for deal in deals:
                revenue = float(deal.get("expected_revenue", 0))
                probability = float(deal.get("probability", 0)) / 100.0
                weighted = revenue * probability

                close_date = deal.get("date_deadline")
                if not close_date:
                    close_date = (date.today() + timedelta(days=60)).isoformat()

                partner_id = deal.get("partner_id")
                if isinstance(partner_id, (list, tuple)):
                    partner_id = partner_id[0]

                if weighted > 0:
                    result.append({
                        "type": "pipeline",
                        "amount": round(weighted, 2),
                        "due_date": str(close_date),
                        "partner_id": partner_id,
                        "reference": deal.get("name", ""),
                        "probability": probability,
                    })
            return result
        except Exception as exc:
            logger.warning("pipeline_fetch_failed", error=str(exc))
            return []

    def _collect_recurring_expenses(self) -> list[dict[str, Any]]:
        """
        Detect recurring expenses by analyzing past vendor bills.
        Groups bills by vendor and identifies monthly patterns.
        """
        try:
            three_months_ago = (date.today() - timedelta(days=90)).isoformat()
            bills = self.fetch_related_records(
                "account.move",
                [
                    ("move_type", "=", "in_invoice"),
                    ("state", "=", "posted"),
                    ("invoice_date", ">=", three_months_ago),
                ],
                fields=["partner_id", "amount_total", "invoice_date", "name"],
                limit=500,
            )

            vendor_bills: dict[int, list[float]] = {}
            for bill in bills:
                partner_id = bill.get("partner_id")
                if isinstance(partner_id, (list, tuple)):
                    partner_id = partner_id[0]
                if not partner_id:
                    continue
                vendor_bills.setdefault(partner_id, []).append(
                    float(bill.get("amount_total", 0))
                )

            result = []
            for vendor_id, amounts in vendor_bills.items():
                if len(amounts) >= 2:
                    avg_amount = sum(amounts) / len(amounts)
                    std_dev = float(np.std(amounts)) if len(amounts) > 1 else 0
                    cv = std_dev / avg_amount if avg_amount > 0 else 1.0

                    if cv < 0.3:
                        result.append({
                            "type": "recurring",
                            "amount": round(avg_amount, 2),
                            "due_date": "",
                            "partner_id": vendor_id,
                            "reference": f"recurring_vendor_{vendor_id}",
                            "frequency": "monthly",
                        })

            return result
        except Exception as exc:
            logger.warning("recurring_expenses_fetch_failed", error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Date-based helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sum_for_date(items: list[dict], target: date) -> float:
        """Sum amounts for items due on the target date."""
        total = 0.0
        target_str = target.isoformat()
        for item in items:
            if item.get("due_date") == target_str:
                total += item["amount"]
        return total

    @staticmethod
    def _recurring_for_date(items: list[dict], target: date) -> float:
        """Spread monthly recurring expenses across the month."""
        if not items:
            return 0.0

        if target.day == 1:
            return sum(item["amount"] for item in items)
        return 0.0

    # ------------------------------------------------------------------
    # Scenario adjustments
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_ar_adjustments(
        ar_data: list[dict], adjustments: dict[str, Any]
    ) -> list[dict]:
        """Apply AR-related adjustments (e.g., delay_customer_X)."""
        result = []
        reduce_pct = float(adjustments.get("reduce_ar_by", 0)) / 100.0

        for item in ar_data:
            new_item = dict(item)
            if reduce_pct > 0:
                new_item["amount"] = round(item["amount"] * (1 - reduce_pct), 2)

            partner_id = item.get("partner_id")
            delay_key = f"delay_customer_{partner_id}"
            if delay_key in adjustments:
                delay_days = int(adjustments[delay_key])
                orig_date = date.fromisoformat(item["due_date"])
                new_item["due_date"] = (orig_date + timedelta(days=delay_days)).isoformat()

            result.append(new_item)
        return result

    @staticmethod
    def _apply_pipeline_adjustments(
        pipeline_data: list[dict], adjustments: dict[str, Any]
    ) -> list[dict]:
        """Apply pipeline adjustments (e.g., remove_deal_X)."""
        result = []
        for item in pipeline_data:
            ref = item.get("reference", "")
            remove_keys = [k for k in adjustments if k.startswith("remove_deal_")]
            skip = False
            for key in remove_keys:
                deal_ref = key.replace("remove_deal_", "")
                if deal_ref in ref or str(item.get("partner_id")) == deal_ref:
                    skip = True
                    break
            if not skip:
                result.append(item)
        return result

    @staticmethod
    def _apply_ap_adjustments(
        ap_data: list[dict], adjustments: dict[str, Any]
    ) -> list[dict]:
        """Apply AP adjustments."""
        increase_pct = float(adjustments.get("increase_ap_by", 0)) / 100.0
        if increase_pct <= 0:
            return ap_data

        result = []
        for item in ap_data:
            new_item = dict(item)
            new_item["amount"] = round(item["amount"] * (1 + increase_pct), 2)
            result.append(new_item)
        return result

    @staticmethod
    def _apply_recurring_adjustments(
        recurring_data: list[dict], adjustments: dict[str, Any]
    ) -> list[dict]:
        """Apply recurring expense adjustments."""
        result = []
        for item in recurring_data:
            new_item = dict(item)
            adj_keys = [k for k in adjustments if k.startswith("adjust_expense_")]
            for key in adj_keys:
                multiplier = float(adjustments[key])
                new_item["amount"] = round(item["amount"] * multiplier, 2)
            result.append(new_item)
        return result

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    def on_create_account_move(
        self, model: str, record_id: int, values: dict[str, Any]
    ) -> AutomationResult:
        """Log AR/AP changes that may affect forecast."""
        move_type = values.get("move_type", "")
        amount = float(values.get("amount_total", 0))

        if move_type in ("out_invoice", "in_invoice"):
            return AutomationResult(
                success=True,
                action="forecast_data_updated",
                model=model,
                record_id=record_id,
                confidence=0.8,
                reasoning=f"New {move_type} for {amount:.2f} — forecast data will be updated on next regeneration",
            )

        return AutomationResult(
            success=True,
            action="forecast_no_action",
            model=model,
            record_id=record_id,
            reasoning="Move type not relevant to forecast",
        )
