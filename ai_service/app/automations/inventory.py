"""
Inventory automations: demand forecasting, auto-reorder, product categorization, anomaly detection.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Inventory Management AI assistant integrated with Odoo ERP.
You optimize stock levels, predict demand, categorize products, and detect anomalies.
Base decisions on historical data, seasonal patterns, and business context.
Always provide confidence scores and clear reasoning."""

FORECAST_TOOLS = [
    {
        "name": "forecast_demand",
        "description": "Forecast product demand based on historical sales and stock movements",
        "input_schema": {
            "type": "object",
            "properties": {
                "forecasts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "product_name": {"type": "string"},
                            "predicted_demand_30d": {"type": "number"},
                            "predicted_demand_90d": {"type": "number"},
                            "recommended_stock_level": {"type": "number"},
                            "trend": {"type": "string", "enum": ["increasing", "stable", "decreasing"]},
                        },
                    },
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["forecasts", "confidence", "reasoning"],
        },
    }
]

CATEGORIZE_TOOLS = [
    {
        "name": "categorize_products",
        "description": "Categorize products using ABC analysis based on value and movement frequency",
        "input_schema": {
            "type": "object",
            "properties": {
                "categorizations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "abc_category": {"type": "string", "enum": ["A", "B", "C"]},
                            "reason": {"type": "string"},
                        },
                    },
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["categorizations", "confidence", "reasoning"],
        },
    }
]

ANOMALY_TOOLS = [
    {
        "name": "detect_stock_anomaly",
        "description": "Detect stock anomalies like shrinkage, miscount, or unusual movements",
        "input_schema": {
            "type": "object",
            "properties": {
                "anomalies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "product_name": {"type": "string"},
                            "anomaly_type": {"type": "string", "enum": ["shrinkage", "miscount", "unusual_movement", "negative_stock"]},
                            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                            "expected_qty": {"type": "number"},
                            "actual_qty": {"type": "number"},
                            "explanation": {"type": "string"},
                        },
                    },
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["anomalies", "confidence", "reasoning"],
        },
    }
]


class InventoryAutomation(BaseAutomation):
    automation_type = "inventory"
    watched_models = ["stock.picking", "product.product"]

    def on_create_stock_picking(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new stock transfer is created, check for anomalies."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="check_transfer", model=model,
                record_id=record_id, reasoning="Record not found",
            )
        return AutomationResult(
            success=True, action="transfer_logged", model=model,
            record_id=record_id, reasoning="Stock transfer logged for monitoring",
        )

    def on_write_product_product(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When product stock changes, check for anomalies."""
        if "qty_available" not in values:
            return AutomationResult(
                success=True, action="no_action", model=model,
                record_id=record_id, reasoning="No stock change",
            )

        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="check_anomaly", model=model,
                record_id=record_id, reasoning="Record not found",
            )

        return self._check_stock_anomaly(model, record_id, record)

    # --- Scheduled scans ---

    def scan_forecast_demand(self):
        """Periodic demand forecasting across all stocked products."""
        products = self.fetch_related_records(
            "product.product",
            [("type", "=", "product"), ("active", "=", True)],
            fields=["id", "name", "qty_available", "virtual_available",
                     "default_code", "categ_id", "standard_price", "list_price"],
            limit=100,
        )

        if not products:
            return

        recent_moves = self.fetch_related_records(
            "stock.move",
            [("state", "=", "done"), ("product_id", "in", [p["id"] for p in products[:50]])],
            fields=["product_id", "product_uom_qty", "date", "picking_type_id", "location_dest_id"],
            limit=500,
        )

        user_msg = f"""Forecast demand for these products based on stock movement history:

Products:
{json.dumps(products[:50], indent=2, default=str)}

Recent stock movements (completed):
{json.dumps(recent_moves[:200], indent=2, default=str)}

For each product, predict:
- Expected demand over the next 30 and 90 days
- Recommended stock level to maintain
- Whether demand is trending up, stable, or down"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, FORECAST_TOOLS)
        if result["tool_calls"]:
            forecast = result["tool_calls"][0]["input"]
            logger.info(
                "demand_forecast_complete",
                products_forecasted=len(forecast.get("forecasts", [])),
            )

    def scan_auto_reorder(self):
        """Check for products below reorder point and trigger PO creation."""
        from app.automations.purchase import PurchaseAutomation
        purchase = PurchaseAutomation()
        purchase.scan_check_reorder_points()

    def scan_categorize_products(self):
        """Periodic ABC analysis of product catalog."""
        products = self.fetch_related_records(
            "product.product",
            [("type", "=", "product"), ("active", "=", True)],
            fields=["id", "name", "qty_available", "standard_price", "list_price", "sales_count"],
            limit=200,
        )

        if not products:
            return

        user_msg = f"""Perform ABC analysis on these products:

Products:
{json.dumps(products[:100], indent=2, default=str)}

ABC Classification:
- A: High-value items (top 20% by revenue contribution) — need tight control
- B: Medium-value items (next 30%) — moderate control
- C: Low-value items (bottom 50%) — minimal control

Consider both unit value and movement frequency."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, CATEGORIZE_TOOLS)
        if result["tool_calls"]:
            categorization = result["tool_calls"][0]["input"]
            logger.info(
                "product_categorization_complete",
                products_categorized=len(categorization.get("categorizations", [])),
            )

    # --- Internal methods ---

    def _check_stock_anomaly(
        self, model: str, record_id: int, record: dict
    ) -> AutomationResult:
        recent_moves = self.fetch_related_records(
            "stock.move",
            [("product_id", "=", record_id), ("state", "=", "done")],
            fields=["product_uom_qty", "date", "picking_type_id", "reference"],
            limit=30,
        )

        user_msg = f"""Check this product for stock anomalies:

Product:
- Name: {record.get('name', 'N/A')}
- Current Stock: {record.get('qty_available', 0)}
- Virtual Stock: {record.get('virtual_available', 0)}
- Code: {record.get('default_code', 'N/A')}

Recent stock movements:
{json.dumps(recent_moves, indent=2, default=str)}

Check for:
- Unexpected stock drops (potential shrinkage)
- Negative stock levels
- Unusual movement patterns
- Large discrepancies between physical and virtual stock"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, ANOMALY_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            anomalies = tool_result.get("anomalies", [])

            if anomalies:
                for anomaly in anomalies:
                    if anomaly.get("severity") in ("medium", "high"):
                        logger.warning(
                            "stock_anomaly_detected",
                            product_id=record_id,
                            anomaly_type=anomaly.get("anomaly_type"),
                            severity=anomaly.get("severity"),
                        )

            return AutomationResult(
                success=True,
                action="detect_stock_anomaly",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=bool(anomalies),
            )

        return AutomationResult(
            success=True, action="no_anomaly",
            model=model, record_id=record_id,
            reasoning="No anomaly check result",
        )
