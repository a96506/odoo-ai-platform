"""
Customer Credit Management — AI credit scoring, limit enforcement, auto-hold/release.

Monitors AR aging in real-time, enforces credit limits on SO creation,
calculates AI credit scores from payment history and order volume,
and auto-releases holds when payment is received.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

RISK_THRESHOLDS = {
    "low": 80.0,
    "normal": 60.0,
    "elevated": 40.0,
    "high": 20.0,
}

WEIGHT_PAYMENT_HISTORY = 0.40
WEIGHT_ORDER_VOLUME = 0.20
WEIGHT_OVERDUE_RATIO = 0.25
WEIGHT_AGE_FACTOR = 0.15

DEFAULT_CREDIT_LIMIT = Decimal("50000.00")

CREDIT_PROMPT = """You are a credit risk analyst for an ERP system. Analyze customer
payment history, order patterns, and overdue amounts to recommend a credit score
and credit limit. Consider industry benchmarks and cash flow impact. Return structured
credit analysis with score, recommended limit, and risk assessment."""

CREDIT_TOOLS = [
    {
        "name": "credit_assessment",
        "description": "Provide credit assessment for a customer",
        "input_schema": {
            "type": "object",
            "properties": {
                "credit_score": {
                    "type": "number",
                    "description": "Credit score 0-100",
                },
                "recommended_limit": {
                    "type": "number",
                    "description": "Recommended credit limit in default currency",
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "normal", "elevated", "high", "critical"],
                    "description": "Overall risk level",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Detailed reasoning for the assessment",
                },
                "hold_recommended": {
                    "type": "boolean",
                    "description": "Whether a credit hold is recommended",
                },
            },
            "required": ["credit_score", "recommended_limit", "risk_level", "reasoning", "hold_recommended"],
        },
    }
]


class CreditManagementAutomation(BaseAutomation):
    """Customer credit management with AI scoring and automatic enforcement."""

    automation_type = "credit_management"
    watched_models = ["sale.order", "account.payment", "account.move"]

    def calculate_credit_score(self, customer_id: int) -> dict[str, Any]:
        """
        Calculate a credit score for a customer using payment history,
        order volume, overdue analysis, and relationship age.
        """
        partner = self.fetch_record_context(
            "res.partner", customer_id,
            ["name", "credit_limit", "total_invoiced", "total_due", "customer_rank", "create_date"],
        )
        if not partner:
            return {"error": f"Customer {customer_id} not found"}

        invoices = self._fetch_customer_invoices(customer_id)
        payments = self._fetch_customer_payments(customer_id)
        open_orders = self._fetch_open_orders(customer_id)

        payment_score = self._score_payment_history(invoices, payments)
        volume_score = self._score_order_volume(invoices, open_orders)
        overdue_score = self._score_overdue_ratio(invoices)
        age_score = self._score_relationship_age(partner)

        composite = (
            payment_score * WEIGHT_PAYMENT_HISTORY
            + volume_score * WEIGHT_ORDER_VOLUME
            + overdue_score * WEIGHT_OVERDUE_RATIO
            + age_score * WEIGHT_AGE_FACTOR
        )
        composite = round(min(max(composite, 0.0), 100.0), 2)

        risk_level = self._classify_risk(composite)
        current_exposure = self._calculate_exposure(invoices, open_orders)
        overdue_amount = self._calculate_overdue(invoices)
        credit_limit = float(partner.get("credit_limit") or DEFAULT_CREDIT_LIMIT)

        hold_active = risk_level in ("high", "critical") or current_exposure > credit_limit

        return {
            "customer_id": customer_id,
            "customer_name": partner.get("name", ""),
            "credit_score": composite,
            "risk_level": risk_level,
            "credit_limit": credit_limit,
            "current_exposure": current_exposure,
            "overdue_amount": overdue_amount,
            "hold_active": hold_active,
            "hold_reason": self._build_hold_reason(risk_level, current_exposure, credit_limit, overdue_amount) if hold_active else None,
            "breakdown": {
                "payment_history": round(payment_score, 2),
                "order_volume": round(volume_score, 2),
                "overdue_ratio": round(overdue_score, 2),
                "relationship_age": round(age_score, 2),
            },
        }

    def check_credit_on_order(
        self, customer_id: int, order_amount: float
    ) -> dict[str, Any]:
        """
        Check if a sales order should be allowed based on the customer's credit.
        Called when a SO is created or confirmed.
        """
        score_data = self.calculate_credit_score(customer_id)
        if "error" in score_data:
            return {"allowed": True, "reason": "Customer not found, allowing by default"}

        credit_limit = score_data["credit_limit"]
        current_exposure = score_data["current_exposure"]
        new_exposure = current_exposure + order_amount

        if score_data["hold_active"]:
            return {
                "allowed": False,
                "reason": f"Customer on credit hold: {score_data['hold_reason']}",
                "credit_score": score_data["credit_score"],
                "risk_level": score_data["risk_level"],
                "current_exposure": current_exposure,
                "credit_limit": credit_limit,
            }

        if new_exposure > credit_limit:
            return {
                "allowed": False,
                "reason": f"Order would exceed credit limit: exposure {new_exposure:.2f} > limit {credit_limit:.2f}",
                "credit_score": score_data["credit_score"],
                "risk_level": score_data["risk_level"],
                "current_exposure": current_exposure,
                "order_amount": order_amount,
                "new_exposure": new_exposure,
                "credit_limit": credit_limit,
                "over_limit_by": round(new_exposure - credit_limit, 2),
            }

        return {
            "allowed": True,
            "reason": "Credit check passed",
            "credit_score": score_data["credit_score"],
            "risk_level": score_data["risk_level"],
            "remaining_credit": round(credit_limit - new_exposure, 2),
        }

    def check_payment_releases(self) -> list[dict[str, Any]]:
        """
        Scan customers on credit hold and check if recent payments
        justify releasing the hold.
        """
        from app.models.audit import CreditScore, get_db_session

        releases = []
        try:
            with get_db_session() as session:
                held = (
                    session.query(CreditScore)
                    .filter(CreditScore.hold_active == True)  # noqa: E712
                    .all()
                )
                for cs in held:
                    refreshed = self.calculate_credit_score(cs.customer_id)
                    if not refreshed.get("hold_active", True):
                        cs.hold_active = False
                        cs.hold_reason = None
                        cs.credit_score = Decimal(str(refreshed["credit_score"]))
                        cs.current_exposure = Decimal(str(refreshed["current_exposure"]))
                        cs.overdue_amount = Decimal(str(refreshed["overdue_amount"]))
                        cs.risk_level = refreshed["risk_level"]
                        cs.last_calculated = datetime.utcnow()
                        releases.append({
                            "customer_id": cs.customer_id,
                            "customer_name": cs.customer_name,
                            "new_score": refreshed["credit_score"],
                            "new_risk": refreshed["risk_level"],
                        })
        except Exception as exc:
            logger.error("payment_release_check_failed", error=str(exc))

        return releases

    def calculate_all_scores(self) -> dict[str, Any]:
        """
        Batch recalculate credit scores for all customers with open AR.
        Intended for daily Celery beat execution.
        """
        from app.models.audit import CreditScore, get_db_session

        customers = self.fetch_related_records(
            "res.partner",
            [("customer_rank", ">", 0), ("active", "=", True)],
            fields=["id", "name"],
            limit=500,
        )

        updated = 0
        errors = 0

        try:
            with get_db_session() as session:
                for cust in customers:
                    try:
                        result = self.calculate_credit_score(cust["id"])
                        if "error" in result:
                            continue

                        existing = (
                            session.query(CreditScore)
                            .filter(CreditScore.customer_id == cust["id"])
                            .first()
                        )

                        if existing:
                            existing.credit_score = Decimal(str(result["credit_score"]))
                            existing.credit_limit = Decimal(str(result["credit_limit"]))
                            existing.current_exposure = Decimal(str(result["current_exposure"]))
                            existing.overdue_amount = Decimal(str(result["overdue_amount"]))
                            existing.payment_history_score = Decimal(str(result["breakdown"]["payment_history"]))
                            existing.order_volume_score = Decimal(str(result["breakdown"]["order_volume"]))
                            existing.risk_level = result["risk_level"]
                            existing.hold_active = result["hold_active"]
                            existing.hold_reason = result.get("hold_reason")
                            existing.last_calculated = datetime.utcnow()
                        else:
                            new_cs = CreditScore(
                                customer_id=cust["id"],
                                customer_name=result["customer_name"],
                                credit_score=Decimal(str(result["credit_score"])),
                                credit_limit=Decimal(str(result["credit_limit"])),
                                current_exposure=Decimal(str(result["current_exposure"])),
                                overdue_amount=Decimal(str(result["overdue_amount"])),
                                payment_history_score=Decimal(str(result["breakdown"]["payment_history"])),
                                order_volume_score=Decimal(str(result["breakdown"]["order_volume"])),
                                risk_level=result["risk_level"],
                                hold_active=result["hold_active"],
                                hold_reason=result.get("hold_reason"),
                            )
                            session.add(new_cs)

                        updated += 1
                    except Exception as exc:
                        errors += 1
                        logger.warning("credit_score_calc_failed", customer_id=cust["id"], error=str(exc))

        except Exception as exc:
            logger.error("batch_credit_scoring_failed", error=str(exc))

        return {
            "total_customers": len(customers),
            "updated": updated,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Scoring components
    # ------------------------------------------------------------------

    @staticmethod
    def _score_payment_history(invoices: list[dict], payments: list[dict]) -> float:
        """Score 0-100 based on on-time payment ratio and late payment severity."""
        if not invoices:
            return 50.0

        paid_invoices = [inv for inv in invoices if inv.get("payment_state") == "paid"]
        if not paid_invoices:
            return 30.0

        on_time = 0
        total = len(paid_invoices)

        for inv in paid_invoices:
            due_date = inv.get("invoice_date_due")
            last_payment_date = inv.get("invoice_date")
            if due_date and last_payment_date:
                if str(last_payment_date) <= str(due_date):
                    on_time += 1
                else:
                    pass
            else:
                on_time += 0.5

        ratio = on_time / total if total > 0 else 0.5
        return min(ratio * 100.0, 100.0)

    @staticmethod
    def _score_order_volume(invoices: list[dict], open_orders: list[dict]) -> float:
        """Score 0-100 based on order frequency and consistency."""
        total_orders = len(invoices) + len(open_orders)
        if total_orders == 0:
            return 30.0
        if total_orders >= 50:
            return 95.0
        if total_orders >= 20:
            return 80.0
        if total_orders >= 10:
            return 65.0
        if total_orders >= 5:
            return 50.0
        return 35.0

    @staticmethod
    def _score_overdue_ratio(invoices: list[dict]) -> float:
        """Score 0-100 — higher is better (less overdue)."""
        open_invoices = [inv for inv in invoices if inv.get("payment_state") in ("not_paid", "partial")]
        if not open_invoices:
            return 100.0

        total_open = sum(float(inv.get("amount_residual", 0)) for inv in open_invoices)
        if total_open <= 0:
            return 100.0

        overdue = 0.0
        today = datetime.utcnow().strftime("%Y-%m-%d")
        for inv in open_invoices:
            due = inv.get("invoice_date_due")
            if due and str(due) < today:
                overdue += float(inv.get("amount_residual", 0))

        overdue_pct = overdue / total_open if total_open > 0 else 0
        return max(0.0, 100.0 * (1 - overdue_pct))

    @staticmethod
    def _score_relationship_age(partner: dict) -> float:
        """Score 0-100 based on how long the customer has been active."""
        create_date = partner.get("create_date")
        if not create_date:
            return 50.0

        try:
            created = datetime.fromisoformat(str(create_date).replace("Z", "+00:00")).replace(tzinfo=None)
            age_days = (datetime.utcnow() - created).days
        except (ValueError, TypeError):
            return 50.0

        if age_days >= 730:
            return 95.0
        if age_days >= 365:
            return 80.0
        if age_days >= 180:
            return 65.0
        if age_days >= 90:
            return 50.0
        return 30.0

    @staticmethod
    def _classify_risk(score: float) -> str:
        if score >= RISK_THRESHOLDS["low"]:
            return "low"
        if score >= RISK_THRESHOLDS["normal"]:
            return "normal"
        if score >= RISK_THRESHOLDS["elevated"]:
            return "elevated"
        if score >= RISK_THRESHOLDS["high"]:
            return "high"
        return "critical"

    @staticmethod
    def _calculate_exposure(invoices: list[dict], open_orders: list[dict]) -> float:
        unpaid = sum(
            float(inv.get("amount_residual", 0))
            for inv in invoices
            if inv.get("payment_state") in ("not_paid", "partial")
        )
        pending = sum(float(o.get("amount_total", 0)) for o in open_orders)
        return round(unpaid + pending, 2)

    @staticmethod
    def _calculate_overdue(invoices: list[dict]) -> float:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return round(
            sum(
                float(inv.get("amount_residual", 0))
                for inv in invoices
                if inv.get("payment_state") in ("not_paid", "partial")
                and inv.get("invoice_date_due")
                and str(inv["invoice_date_due"]) < today
            ),
            2,
        )

    @staticmethod
    def _build_hold_reason(
        risk_level: str, exposure: float, limit: float, overdue: float
    ) -> str:
        reasons = []
        if risk_level in ("high", "critical"):
            reasons.append(f"Risk level: {risk_level}")
        if exposure > limit:
            reasons.append(f"Exposure ({exposure:.2f}) exceeds limit ({limit:.2f})")
        if overdue > 0:
            reasons.append(f"Overdue amount: {overdue:.2f}")
        return "; ".join(reasons) if reasons else "Credit hold applied"

    # ------------------------------------------------------------------
    # Odoo data fetching
    # ------------------------------------------------------------------

    def _fetch_customer_invoices(self, customer_id: int) -> list[dict]:
        return self.fetch_related_records(
            "account.move",
            [
                ("partner_id", "=", customer_id),
                ("move_type", "in", ["out_invoice", "out_refund"]),
                ("state", "=", "posted"),
            ],
            fields=["name", "amount_total", "amount_residual", "payment_state",
                     "invoice_date", "invoice_date_due", "move_type"],
            limit=200,
        )

    def _fetch_customer_payments(self, customer_id: int) -> list[dict]:
        return self.fetch_related_records(
            "account.payment",
            [
                ("partner_id", "=", customer_id),
                ("payment_type", "=", "inbound"),
                ("state", "=", "posted"),
            ],
            fields=["name", "amount", "date", "payment_type"],
            limit=200,
        )

    def _fetch_open_orders(self, customer_id: int) -> list[dict]:
        return self.fetch_related_records(
            "sale.order",
            [
                ("partner_id", "=", customer_id),
                ("state", "in", ["sale", "done"]),
                ("invoice_status", "!=", "invoiced"),
            ],
            fields=["name", "amount_total", "state", "invoice_status"],
            limit=100,
        )

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    def on_create_sale_order(self, model: str, record_id: int, values: dict[str, Any]) -> AutomationResult:
        """Check credit when a new SO is created."""
        partner_id = values.get("partner_id")
        amount = float(values.get("amount_total", 0))

        if not partner_id:
            return AutomationResult(
                success=True, action="credit_check_skipped", model=model,
                record_id=record_id, reasoning="No partner on order",
            )

        check = self.check_credit_on_order(partner_id, amount)
        if check["allowed"]:
            return AutomationResult(
                success=True, action="credit_check_passed", model=model,
                record_id=record_id, confidence=1.0,
                reasoning=check["reason"],
                changes_made=check,
            )

        return AutomationResult(
            success=True, action="credit_check_failed", model=model,
            record_id=record_id, confidence=0.95,
            reasoning=check["reason"],
            changes_made=check,
            needs_approval=True,
        )

    def on_create_account_payment(self, model: str, record_id: int, values: dict[str, Any]) -> AutomationResult:
        """When a payment is received, check if it releases any credit holds."""
        partner_id = values.get("partner_id")
        if not partner_id:
            return AutomationResult(
                success=True, action="payment_no_partner", model=model,
                record_id=record_id, reasoning="Payment has no partner",
            )

        score_data = self.calculate_credit_score(partner_id)
        if "error" in score_data:
            return AutomationResult(
                success=False, action="credit_recalc_failed", model=model,
                record_id=record_id, reasoning=score_data["error"],
            )

        return AutomationResult(
            success=True, action="credit_recalculated", model=model,
            record_id=record_id, confidence=0.9,
            reasoning=f"Credit recalculated after payment: score={score_data['credit_score']}, risk={score_data['risk_level']}",
            changes_made=score_data,
        )
