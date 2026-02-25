"""
Sales automations: quotation generation, pricing optimization, pipeline forecasting.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Sales AI assistant integrated with Odoo ERP.
You help optimize the sales process by analyzing orders, suggesting pricing,
forecasting pipeline outcomes, and identifying upsell opportunities.
Always provide confidence scores and clear reasoning."""

QUOTATION_TOOLS = [
    {
        "name": "generate_quotation_lines",
        "description": "Suggest product lines for a quotation based on customer history and context",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggested_lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "product_name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "price_unit": {"type": "number"},
                            "discount": {"type": "number"},
                        },
                    },
                    "description": "Suggested order lines",
                },
                "upsell_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional product suggestions for upselling",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["suggested_lines", "upsell_suggestions", "confidence", "reasoning"],
        },
    }
]

PRICING_TOOLS = [
    {
        "name": "optimize_pricing",
        "description": "Suggest optimal pricing and discounts for a sales order",
        "input_schema": {
            "type": "object",
            "properties": {
                "line_adjustments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "line_id": {"type": "integer"},
                            "suggested_price": {"type": "number"},
                            "suggested_discount": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                    },
                    "description": "Price/discount adjustments per line",
                },
                "total_impact": {"type": "number", "description": "Net revenue impact"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["line_adjustments", "total_impact", "confidence", "reasoning"],
        },
    }
]

FORECAST_TOOLS = [
    {
        "name": "forecast_pipeline",
        "description": "Forecast sales pipeline outcomes and flag at-risk deals",
        "input_schema": {
            "type": "object",
            "properties": {
                "at_risk_deals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "integer"},
                            "order_name": {"type": "string"},
                            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                            "risk_factors": {"type": "array", "items": {"type": "string"}},
                            "suggested_action": {"type": "string"},
                        },
                    },
                },
                "expected_close_value": {"type": "number", "description": "Total expected close value"},
                "expected_close_count": {"type": "integer", "description": "Number of deals expected to close"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["at_risk_deals", "expected_close_value", "expected_close_count", "confidence", "reasoning"],
        },
    }
]


class SalesAutomation(BaseAutomation):
    automation_type = "sales"
    watched_models = ["sale.order"]

    def on_create_sale_order(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new quotation is created, suggest products and pricing."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="suggest_products",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        partner_id = record.get("partner_id")
        if isinstance(partner_id, (list, tuple)):
            partner_id = partner_id[0]

        if not partner_id:
            return AutomationResult(
                success=True, action="no_action",
                model=model, record_id=record_id,
                reasoning="No partner set, skipping suggestions",
            )

        order_lines = self.fetch_related_records(
            "sale.order.line",
            [("order_id", "=", record_id)],
            fields=["product_id", "product_uom_qty", "price_unit", "discount"],
        )

        if order_lines:
            return self._optimize_pricing(model, record_id, record, order_lines)
        else:
            return self._suggest_products(model, record_id, record, partner_id)

    def on_write_sale_order(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a quotation is updated, re-check pricing if lines changed."""
        if "state" in values and values.get("state") == "sale":
            return AutomationResult(
                success=True, action="order_confirmed",
                model=model, record_id=record_id,
                reasoning="Order confirmed, no further optimization needed",
            )

        return AutomationResult(
            success=True, action="no_action",
            model=model, record_id=record_id,
            reasoning="No significant change requiring AI action",
        )

    # --- Scheduled scans ---

    def scan_forecast_pipeline(self):
        """Periodic pipeline forecast and at-risk deal detection."""
        open_orders = self.fetch_related_records(
            "sale.order",
            [("state", "in", ["draft", "sent"])],
            fields=[
                "name", "partner_id", "amount_total", "date_order",
                "validity_date", "user_id", "create_date",
            ],
            limit=100,
        )

        if not open_orders:
            return

        won_history = self.fetch_related_records(
            "sale.order",
            [("state", "=", "sale")],
            fields=["partner_id", "amount_total", "date_order", "create_date"],
            limit=50,
        )

        user_msg = f"""Analyze the current sales pipeline and identify at-risk deals:

Open quotations/orders:
{json.dumps(open_orders, indent=2, default=str)}

Recent won orders for context:
{json.dumps(won_history[:30], indent=2, default=str)}

For each open deal, assess:
- Risk of losing (based on age, amount, validity date)
- Suggested actions to improve chances
- Expected close probability

Provide an overall pipeline forecast."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, FORECAST_TOOLS)
        if result["tool_calls"]:
            forecast = result["tool_calls"][0]["input"]
            for deal in forecast.get("at_risk_deals", []):
                if deal.get("risk_level") in ("medium", "high"):
                    order_id = deal.get("order_id")
                    if order_id:
                        self.update_record("sale.order", order_id, {
                            "note": f"⚠️ AI Risk Alert [{deal['risk_level'].upper()}]: "
                            f"{', '.join(deal.get('risk_factors', []))}. "
                            f"Suggested: {deal.get('suggested_action', 'Review')}"
                        })

            logger.info(
                "pipeline_forecast_complete",
                at_risk=len(forecast.get("at_risk_deals", [])),
                expected_value=forecast.get("expected_close_value", 0),
            )

    # --- Internal methods ---

    def _suggest_products(
        self, model: str, record_id: int, record: dict, partner_id: int
    ) -> AutomationResult:
        past_orders = self.fetch_related_records(
            "sale.order",
            [("partner_id", "=", partner_id), ("state", "=", "sale")],
            fields=["name", "amount_total", "date_order"],
            limit=10,
        )

        past_lines = []
        if past_orders:
            order_ids = [o["id"] for o in past_orders]
            past_lines = self.fetch_related_records(
                "sale.order.line",
                [("order_id", "in", order_ids)],
                fields=["product_id", "product_uom_qty", "price_unit"],
                limit=100,
            )

        products = self.fetch_related_records(
            "product.product",
            [("sale_ok", "=", True), ("active", "=", True)],
            fields=["id", "name", "list_price", "categ_id"],
            limit=100,
        )

        user_msg = f"""Suggest products for a new quotation:

Customer: {record.get('partner_id', 'Unknown')}

Customer's past orders:
{json.dumps(past_orders, indent=2, default=str)}

Products they've ordered before:
{json.dumps(past_lines[:50], indent=2, default=str)}

Available products catalog:
{json.dumps(products[:50], indent=2, default=str)}

Based on purchase history, suggest:
1. Products they're likely to reorder
2. Appropriate quantities based on patterns
3. Upsell/cross-sell opportunities"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, QUOTATION_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="suggest_products",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=True,
            )

        return AutomationResult(
            success=False, action="suggest_products",
            model=model, record_id=record_id,
            reasoning="Failed to generate product suggestions",
        )

    def _optimize_pricing(
        self, model: str, record_id: int, record: dict, order_lines: list
    ) -> AutomationResult:
        partner_id = record.get("partner_id")
        if isinstance(partner_id, (list, tuple)):
            partner_id = partner_id[0]

        competitor_context = ""
        past_discounts = self.fetch_related_records(
            "sale.order.line",
            [
                ("order_id.partner_id", "=", partner_id),
                ("order_id.state", "=", "sale"),
                ("discount", ">", 0),
            ],
            fields=["product_id", "discount", "price_unit"],
            limit=30,
        )
        if past_discounts:
            competitor_context = f"\nPast discounts given to this customer:\n{json.dumps(past_discounts, indent=2, default=str)}"

        user_msg = f"""Optimize pricing for this sales order:

Order: {record.get('name', 'N/A')}
Customer: {record.get('partner_id', 'Unknown')}
Total: {record.get('amount_total', 0)}

Current order lines:
{json.dumps(order_lines, indent=2, default=str)}
{competitor_context}

Suggest optimal pricing adjustments:
- Consider customer relationship value
- Balance margin with win probability
- Suggest strategic discounts where they'd help close the deal"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, PRICING_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="optimize_pricing",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=True,
            )

        return AutomationResult(
            success=False, action="optimize_pricing",
            model=model, record_id=record_id,
            reasoning="Failed to optimize pricing",
        )
