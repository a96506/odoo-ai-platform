"""
Supply Chain Intelligence automation.

Provides:
- Supplier risk scoring (7 weighted factors)
- Delivery degradation detection (rolling window analysis)
- Single-source risk identification
- Alternative supplier mapping

Runs as scheduled Celery beat tasks + real-time updates on delivery events.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Any

import structlog

from app.automations.base import BaseAutomation
from app.models.audit import (
    SupplierRiskScore,
    SupplierRiskFactor,
    DisruptionPrediction,
    SupplyChainAlert,
    AlternativeSupplierMap,
    RiskClassification,
    AlertSeverity,
    get_db_session,
)

logger = structlog.get_logger()

RISK_WEIGHTS = {
    "delivery_performance": 0.30,
    "quality_acceptance": 0.20,
    "financial_health": 0.15,
    "price_stability": 0.10,
    "geographic_risk": 0.10,
    "dependency_concentration": 0.10,
    "communication_responsiveness": 0.05,
}


def _classify_risk(score: float) -> RiskClassification:
    if score >= 80:
        return RiskClassification.LOW
    elif score >= 60:
        return RiskClassification.WATCH
    elif score >= 40:
        return RiskClassification.ELEVATED
    else:
        return RiskClassification.CRITICAL


class SupplyChainAutomation(BaseAutomation):
    automation_type = "supply_chain"
    watched_models = ["stock.picking"]

    # ------------------------------------------------------------------
    # Public API — called by Celery tasks
    # ------------------------------------------------------------------

    def calculate_all_risk_scores(self) -> dict[str, Any]:
        """Daily: recalculate risk scores for all active vendors."""
        vendors = self._get_active_vendors()
        results = {"vendors_scored": 0, "critical": 0, "elevated": 0, "watch": 0, "low": 0, "errors": 0}

        for vendor in vendors:
            try:
                score = self._calculate_vendor_risk(vendor)
                classification = _classify_risk(score["composite"])
                self._persist_risk_score(vendor["id"], score, classification)
                results["vendors_scored"] += 1
                results[classification.value] = results.get(classification.value, 0) + 1
            except Exception as exc:
                results["errors"] += 1
                logger.warning("vendor_risk_score_failed", vendor_id=vendor["id"], error=str(exc))

        return results

    def detect_delivery_degradation(self) -> list[dict[str, Any]]:
        """Every 6 hours: identify vendors with worsening delivery patterns."""
        vendors = self._get_active_vendors()
        predictions = []

        for vendor in vendors:
            try:
                degradation = self._check_degradation(vendor["id"])
                if degradation and degradation["is_degrading"]:
                    prediction = self._create_disruption_prediction(vendor, degradation)
                    predictions.append(prediction)
            except Exception as exc:
                logger.warning("degradation_check_failed", vendor_id=vendor["id"], error=str(exc))

        return predictions

    def detect_single_source_risks(self) -> dict[str, Any]:
        """Weekly: find products with only one supplier."""
        try:
            supplier_info = self.odoo.search_read(
                "product.supplierinfo",
                [("partner_id.supplier_rank", ">", 0)],
                fields=["product_tmpl_id", "partner_id", "price", "delay"],
                limit=10000,
            )
        except Exception:
            supplier_info = []

        product_vendors: dict[int, list] = defaultdict(list)
        for si in supplier_info:
            tmpl = si.get("product_tmpl_id")
            tmpl_id = tmpl[0] if isinstance(tmpl, (list, tuple)) else tmpl
            if tmpl_id:
                partner = si.get("partner_id")
                partner_id = partner[0] if isinstance(partner, (list, tuple)) else partner
                product_vendors[tmpl_id].append({
                    "vendor_id": partner_id,
                    "price": si.get("price", 0),
                    "delay": si.get("delay", 0),
                })

        single_source = []
        for tmpl_id, vendors in product_vendors.items():
            unique_vendors = set(v["vendor_id"] for v in vendors)
            if len(unique_vendors) == 1:
                single_source.append({"product_tmpl_id": tmpl_id, "vendor_id": list(unique_vendors)[0]})

        revenue_at_risk = 0.0
        for ss in single_source:
            try:
                sales = self.odoo.search_read(
                    "sale.order.line",
                    [
                        ("product_template_id", "=", ss["product_tmpl_id"]),
                        ("order_id.state", "in", ["sale", "done"]),
                        ("order_id.date_order", ">=", (date.today() - timedelta(days=365)).isoformat()),
                    ],
                    fields=["price_subtotal"],
                    limit=1000,
                )
                ss["annual_revenue"] = sum(s.get("price_subtotal", 0) for s in sales)
                revenue_at_risk += ss["annual_revenue"]
            except Exception:
                ss["annual_revenue"] = 0

        self._persist_single_source_alerts(single_source)

        return {
            "single_source_products": len(single_source),
            "total_products_assessed": len(product_vendors),
            "total_revenue_at_risk": round(revenue_at_risk, 2),
            "details": single_source[:50],
        }

    # ------------------------------------------------------------------
    # Risk score calculation — 7 factors
    # ------------------------------------------------------------------

    def _calculate_vendor_risk(self, vendor: dict) -> dict[str, Any]:
        vendor_id = vendor["id"]
        factors: dict[str, float] = {}

        factors["delivery_performance"] = self._score_delivery_performance(vendor_id)
        factors["quality_acceptance"] = self._score_quality_acceptance(vendor_id)
        factors["price_stability"] = self._score_price_stability(vendor_id)
        factors["financial_health"] = self._score_financial_health(vendor)
        factors["geographic_risk"] = self._score_geographic_risk(vendor)
        factors["dependency_concentration"] = self._score_dependency_concentration(vendor_id)
        factors["communication_responsiveness"] = self._score_communication(vendor_id)

        composite = sum(
            factors[factor] * weight
            for factor, weight in RISK_WEIGHTS.items()
        )

        return {"composite": round(composite, 2), "factors": factors}

    def _score_delivery_performance(self, vendor_id: int) -> float:
        """Score 0-100 based on on-time delivery rate over last 6 months."""
        try:
            six_months_ago = (date.today() - timedelta(days=180)).isoformat()
            pickings = self.odoo.search_read(
                "stock.picking",
                [
                    ("partner_id", "=", vendor_id),
                    ("picking_type_code", "=", "incoming"),
                    ("state", "=", "done"),
                    ("date_done", ">=", six_months_ago),
                ],
                fields=["scheduled_date", "date_done"],
                limit=500,
            )
        except Exception:
            return 70.0

        if not pickings:
            return 70.0

        on_time = 0
        for p in pickings:
            scheduled = p.get("scheduled_date", "")
            done = p.get("date_done", "")
            if scheduled and done:
                try:
                    sched = datetime.fromisoformat(str(scheduled).replace("Z", "+00:00")) if isinstance(scheduled, str) else scheduled
                    actual = datetime.fromisoformat(str(done).replace("Z", "+00:00")) if isinstance(done, str) else done
                    if actual <= sched + timedelta(days=1):
                        on_time += 1
                except (ValueError, TypeError):
                    on_time += 1
            else:
                on_time += 1

        rate = on_time / len(pickings) if pickings else 1.0
        return round(rate * 100, 1)

    def _score_quality_acceptance(self, vendor_id: int) -> float:
        """Score based on ratio of accepted vs returned quantities."""
        try:
            six_months_ago = (date.today() - timedelta(days=180)).isoformat()
            incoming = self.odoo.search_read(
                "stock.picking",
                [
                    ("partner_id", "=", vendor_id),
                    ("picking_type_code", "=", "incoming"),
                    ("state", "=", "done"),
                    ("date_done", ">=", six_months_ago),
                ],
                fields=["id"],
                limit=500,
            )
            returns = self.odoo.search_read(
                "stock.picking",
                [
                    ("partner_id", "=", vendor_id),
                    ("picking_type_code", "=", "outgoing"),
                    ("origin", "ilike", "Return"),
                    ("state", "=", "done"),
                    ("date_done", ">=", six_months_ago),
                ],
                fields=["id"],
                limit=500,
            )
        except Exception:
            return 85.0

        total = len(incoming)
        if total == 0:
            return 85.0

        return_rate = len(returns) / total
        return round(max(0, (1 - return_rate * 10)) * 100, 1)

    def _score_price_stability(self, vendor_id: int) -> float:
        """Score based on price change volatility over the past year."""
        try:
            one_year_ago = (date.today() - timedelta(days=365)).isoformat()
            po_lines = self.odoo.search_read(
                "purchase.order.line",
                [
                    ("partner_id", "=", vendor_id),
                    ("order_id.state", "in", ["purchase", "done"]),
                    ("order_id.date_order", ">=", one_year_ago),
                ],
                fields=["product_id", "price_unit"],
                limit=1000,
            )
        except Exception:
            return 80.0

        if len(po_lines) < 3:
            return 80.0

        product_prices: dict[int, list[float]] = defaultdict(list)
        for line in po_lines:
            prod = line.get("product_id")
            prod_id = prod[0] if isinstance(prod, (list, tuple)) else prod
            if prod_id:
                product_prices[prod_id].append(line.get("price_unit", 0))

        cvs = []
        for prices in product_prices.values():
            if len(prices) >= 2:
                mean = sum(prices) / len(prices)
                if mean > 0:
                    std = math.sqrt(sum((p - mean) ** 2 for p in prices) / len(prices))
                    cvs.append(std / mean)

        if not cvs:
            return 80.0

        avg_cv = sum(cvs) / len(cvs)
        return round(max(0, min(100, (1 - avg_cv * 5) * 100)), 1)

    def _score_financial_health(self, vendor: dict) -> float:
        """Placeholder — returns baseline; Phase 3 adds external API integration."""
        return 70.0

    def _score_geographic_risk(self, vendor: dict) -> float:
        """Placeholder — returns baseline; Phase 3 adds geopolitical risk data."""
        return 75.0

    def _score_dependency_concentration(self, vendor_id: int) -> float:
        """Score based on what % of total spend goes to this vendor."""
        try:
            one_year_ago = (date.today() - timedelta(days=365)).isoformat()
            vendor_spend = self.odoo.search_read(
                "purchase.order",
                [
                    ("partner_id", "=", vendor_id),
                    ("state", "in", ["purchase", "done"]),
                    ("date_order", ">=", one_year_ago),
                ],
                fields=["amount_total"],
                limit=1000,
            )
            total_spend = self.odoo.search_read(
                "purchase.order",
                [
                    ("state", "in", ["purchase", "done"]),
                    ("date_order", ">=", one_year_ago),
                ],
                fields=["amount_total"],
                limit=10000,
            )
        except Exception:
            return 80.0

        vendor_total = sum(po.get("amount_total", 0) for po in vendor_spend)
        all_total = sum(po.get("amount_total", 0) for po in total_spend)

        if all_total == 0:
            return 80.0

        concentration = vendor_total / all_total
        if concentration > 0.5:
            return 20.0
        elif concentration > 0.3:
            return 50.0
        elif concentration > 0.15:
            return 70.0
        return 90.0

    def _score_communication(self, vendor_id: int) -> float:
        """Score based on PO acknowledgment speed (date_approve - date_order)."""
        try:
            six_months_ago = (date.today() - timedelta(days=180)).isoformat()
            pos = self.odoo.search_read(
                "purchase.order",
                [
                    ("partner_id", "=", vendor_id),
                    ("state", "in", ["purchase", "done"]),
                    ("date_approve", "!=", False),
                    ("date_order", ">=", six_months_ago),
                ],
                fields=["date_order", "date_approve"],
                limit=100,
            )
        except Exception:
            return 70.0

        if not pos:
            return 70.0

        response_days = []
        for po in pos:
            try:
                ordered = datetime.fromisoformat(str(po["date_order"]).replace("Z", "+00:00"))
                approved = datetime.fromisoformat(str(po["date_approve"]).replace("Z", "+00:00"))
                diff = (approved - ordered).days
                response_days.append(max(0, diff))
            except (ValueError, TypeError, KeyError):
                pass

        if not response_days:
            return 70.0

        avg_days = sum(response_days) / len(response_days)
        if avg_days <= 1:
            return 95.0
        elif avg_days <= 3:
            return 80.0
        elif avg_days <= 7:
            return 60.0
        elif avg_days <= 14:
            return 40.0
        return 20.0

    # ------------------------------------------------------------------
    # Disruption detection
    # ------------------------------------------------------------------

    def _check_degradation(self, vendor_id: int) -> dict[str, Any] | None:
        """Compare recent (30-day) delivery performance to historical (90-day)."""
        try:
            now = date.today()
            recent_start = (now - timedelta(days=30)).isoformat()
            historical_start = (now - timedelta(days=90)).isoformat()

            recent = self.odoo.search_read(
                "stock.picking",
                [
                    ("partner_id", "=", vendor_id),
                    ("picking_type_code", "=", "incoming"),
                    ("state", "=", "done"),
                    ("date_done", ">=", recent_start),
                ],
                fields=["scheduled_date", "date_done"],
                limit=100,
            )
            historical = self.odoo.search_read(
                "stock.picking",
                [
                    ("partner_id", "=", vendor_id),
                    ("picking_type_code", "=", "incoming"),
                    ("state", "=", "done"),
                    ("date_done", ">=", historical_start),
                    ("date_done", "<", recent_start),
                ],
                fields=["scheduled_date", "date_done"],
                limit=500,
            )
        except Exception:
            return None

        if len(recent) < 3 or len(historical) < 5:
            return None

        recent_delays = self._compute_avg_delay(recent)
        historical_delays = self._compute_avg_delay(historical)

        if historical_delays == 0:
            return None

        degradation_ratio = recent_delays / max(historical_delays, 0.1)
        is_degrading = degradation_ratio > 1.5 and recent_delays > 2

        return {
            "is_degrading": is_degrading,
            "recent_avg_delay_days": round(recent_delays, 1),
            "historical_avg_delay_days": round(historical_delays, 1),
            "degradation_ratio": round(degradation_ratio, 2),
            "recent_deliveries": len(recent),
            "historical_deliveries": len(historical),
        }

    @staticmethod
    def _compute_avg_delay(pickings: list[dict]) -> float:
        delays = []
        for p in pickings:
            sched = p.get("scheduled_date", "")
            done = p.get("date_done", "")
            if sched and done:
                try:
                    s = datetime.fromisoformat(str(sched).replace("Z", "+00:00"))
                    d = datetime.fromisoformat(str(done).replace("Z", "+00:00"))
                    delay = max(0, (d - s).days)
                    delays.append(delay)
                except (ValueError, TypeError):
                    pass
        return sum(delays) / len(delays) if delays else 0.0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_risk_score(
        self,
        vendor_id: int,
        score_data: dict[str, Any],
        classification: RiskClassification,
    ):
        with get_db_session() as session:
            risk_score = SupplierRiskScore(
                vendor_id=vendor_id,
                composite_score=score_data["composite"],
                classification=classification,
                factor_scores=score_data["factors"],
            )
            session.add(risk_score)
            session.flush()

            for factor_name, factor_value in score_data["factors"].items():
                factor = SupplierRiskFactor(
                    risk_score_id=risk_score.id,
                    factor_name=factor_name,
                    factor_value=factor_value,
                    weight=RISK_WEIGHTS.get(factor_name, 0),
                )
                session.add(factor)

    def _create_disruption_prediction(
        self,
        vendor: dict,
        degradation: dict[str, Any],
    ) -> dict[str, Any]:
        severity = AlertSeverity.HIGH if degradation["degradation_ratio"] > 2.0 else AlertSeverity.MEDIUM
        probability = min(0.95, degradation["degradation_ratio"] / 3.0)

        with get_db_session() as session:
            prediction = DisruptionPrediction(
                vendor_id=vendor["id"],
                prediction_type="delivery_delay",
                probability=round(probability, 2),
                estimated_impact=f"Avg delay increased from {degradation['historical_avg_delay_days']}d to {degradation['recent_avg_delay_days']}d",
                recommended_actions=[
                    "Contact vendor for root cause assessment",
                    "Review alternative suppliers",
                    "Consider increasing safety stock for affected products",
                ],
            )
            session.add(prediction)

            alert = SupplyChainAlert(
                vendor_id=vendor["id"],
                alert_type="delivery_degradation",
                severity=severity,
                title=f"Delivery degradation: {vendor.get('name', 'Vendor ' + str(vendor.get('id', '?')))}",
                description=(
                    f"Average delivery delay increased from "
                    f"{degradation['historical_avg_delay_days']:.1f} days to "
                    f"{degradation['recent_avg_delay_days']:.1f} days "
                    f"({degradation['degradation_ratio']:.1f}x degradation)"
                ),
            )
            session.add(alert)

        return {
            "vendor_id": vendor["id"],
            "vendor_name": vendor.get("name", ""),
            "severity": severity.value,
            "degradation": degradation,
        }

    def _persist_single_source_alerts(self, single_source: list[dict]):
        with get_db_session() as session:
            for ss in single_source[:100]:
                alert = SupplyChainAlert(
                    vendor_id=ss["vendor_id"],
                    alert_type="single_source_risk",
                    severity=AlertSeverity.MEDIUM if ss.get("annual_revenue", 0) < 100000 else AlertSeverity.HIGH,
                    title=f"Single-source risk: product template {ss['product_tmpl_id']}",
                    description=f"Product has only one supplier (vendor {ss['vendor_id']}), annual revenue at risk: {ss.get('annual_revenue', 0):.2f}",
                )
                session.add(alert)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_active_vendors(self) -> list[dict]:
        try:
            return self.odoo.search_read(
                "res.partner",
                [("supplier_rank", ">", 0), ("active", "=", True)],
                fields=["id", "name", "country_id", "supplier_rank"],
                limit=1000,
            )
        except Exception:
            return []
