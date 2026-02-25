"""
Purchase automations: auto-PO creation, vendor selection, bill matching.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Procurement AI assistant integrated with Odoo ERP.
You optimize purchasing decisions by analyzing vendor performance, pricing history,
and stock levels. Always provide confidence scores and clear reasoning.
Prioritize cost savings while maintaining quality and reliable delivery."""

VENDOR_TOOLS = [
    {
        "name": "select_vendor",
        "description": "Select the best vendor for a product based on price, delivery, and quality",
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_id": {
                    "type": "integer",
                    "description": "Selected res.partner vendor ID",
                },
                "vendor_name": {"type": "string"},
                "unit_price": {"type": "number", "description": "Recommended unit price"},
                "lead_time_days": {"type": "integer"},
                "alternatives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "vendor_id": {"type": "integer"},
                            "vendor_name": {"type": "string"},
                            "price": {"type": "number"},
                            "reason_not_selected": {"type": "string"},
                        },
                    },
                    "description": "Alternative vendors considered",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["vendor_id", "vendor_name", "unit_price", "lead_time_days", "confidence", "reasoning"],
        },
    }
]

AUTO_PO_TOOLS = [
    {
        "name": "create_purchase_order",
        "description": "Generate a purchase order for products below reorder point",
        "input_schema": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "integer"},
                            "product_name": {"type": "string"},
                            "quantity": {"type": "number"},
                            "vendor_id": {"type": "integer"},
                            "estimated_price": {"type": "number"},
                        },
                    },
                    "description": "Purchase order lines to create",
                },
                "total_estimated_cost": {"type": "number"},
                "urgency": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["lines", "total_estimated_cost", "urgency", "confidence", "reasoning"],
        },
    }
]

BILL_MATCH_TOOLS = [
    {
        "name": "match_vendor_bill",
        "description": "Match an incoming vendor bill to existing purchase orders",
        "input_schema": {
            "type": "object",
            "properties": {
                "matched_po_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Purchase order IDs matching this bill",
                },
                "match_type": {
                    "type": "string",
                    "enum": ["exact", "partial", "overage", "none"],
                },
                "discrepancies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any discrepancies found between bill and PO",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["matched_po_ids", "match_type", "discrepancies", "confidence", "reasoning"],
        },
    }
]


class PurchaseAutomation(BaseAutomation):
    automation_type = "purchase"
    watched_models = ["purchase.order"]

    def on_create_purchase_order(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a PO is manually created, optimize vendor selection."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="optimize_po",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        lines = self.fetch_related_records(
            "purchase.order.line",
            [("order_id", "=", record_id)],
            fields=["product_id", "product_qty", "price_unit", "product_uom"],
        )

        if not lines:
            return AutomationResult(
                success=True, action="no_action",
                model=model, record_id=record_id,
                reasoning="No order lines to optimize",
            )

        return self._optimize_vendor_for_po(model, record_id, record, lines)

    def on_write_purchase_order(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a PO is confirmed, log for bill matching later."""
        return AutomationResult(
            success=True, action="no_action",
            model=model, record_id=record_id,
            reasoning="PO update logged",
        )

    # --- Scheduled scans ---

    def scan_check_reorder_points(self):
        """Check products below reorder point and suggest purchase orders."""
        products_below = self.fetch_related_records(
            "product.product",
            [
                ("type", "=", "product"),
                ("active", "=", True),
            ],
            fields=[
                "id", "name", "qty_available", "virtual_available",
                "default_code", "categ_id", "standard_price",
            ],
            limit=200,
        )

        reorder_rules = self.fetch_related_records(
            "stock.warehouse.orderpoint",
            [("active", "=", True)],
            fields=["product_id", "product_min_qty", "product_max_qty", "qty_to_order"],
            limit=200,
        )

        rule_by_product = {}
        for rule in reorder_rules:
            pid = rule["product_id"]
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            rule_by_product[pid] = rule

        needs_reorder = []
        for product in products_below:
            rule = rule_by_product.get(product["id"])
            if rule:
                if product.get("qty_available", 0) <= rule.get("product_min_qty", 0):
                    needs_reorder.append({
                        **product,
                        "min_qty": rule.get("product_min_qty", 0),
                        "max_qty": rule.get("product_max_qty", 0),
                    })

        if not needs_reorder:
            logger.info("reorder_scan_complete", needs_reorder=0)
            return

        vendor_info = self.fetch_related_records(
            "product.supplierinfo",
            [("product_id", "in", [p["id"] for p in needs_reorder])],
            fields=["product_id", "partner_id", "price", "delay", "min_qty"],
            limit=200,
        )

        user_msg = f"""Products below reorder point need purchase orders:

Products needing restock:
{json.dumps(needs_reorder, indent=2, default=str)}

Available vendor information:
{json.dumps(vendor_info, indent=2, default=str)}

Group items by vendor where possible to minimize shipping costs.
Calculate optimal quantities (enough to reach max stock level).
Set urgency based on how far below minimum the stock is."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, AUTO_PO_TOOLS)

        if result["tool_calls"]:
            po_data = result["tool_calls"][0]["input"]
            confidence = po_data.get("confidence", 0)

            if self.should_auto_execute(confidence) and po_data.get("urgency") != "critical":
                self._create_purchase_orders(po_data)
            else:
                logger.info(
                    "reorder_needs_approval",
                    lines=len(po_data.get("lines", [])),
                    total=po_data.get("total_estimated_cost", 0),
                )

    # --- Internal methods ---

    def _optimize_vendor_for_po(
        self, model: str, record_id: int, record: dict, lines: list
    ) -> AutomationResult:
        product_ids = []
        for line in lines:
            pid = line.get("product_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid:
                product_ids.append(pid)

        vendor_info = self.fetch_related_records(
            "product.supplierinfo",
            [("product_id", "in", product_ids)],
            fields=["product_id", "partner_id", "price", "delay", "min_qty"],
            limit=100,
        )

        past_pos = self.fetch_related_records(
            "purchase.order",
            [("state", "=", "purchase")],
            fields=["partner_id", "amount_total", "date_order", "date_planned"],
            limit=30,
        )

        user_msg = f"""Optimize vendor selection for this purchase order:

Current PO:
- Vendor: {record.get('partner_id', 'N/A')}
- Total: {record.get('amount_total', 0)}

Order lines:
{json.dumps(lines, indent=2, default=str)}

Available vendors and pricing:
{json.dumps(vendor_info, indent=2, default=str)}

Recent purchase history:
{json.dumps(past_pos[:15], indent=2, default=str)}

Select the best vendor considering:
- Best price for required quantities
- Delivery lead time
- Historical reliability (inferred from past order patterns)
- Minimum order quantities"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, VENDOR_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="select_vendor",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=True,
            )

        return AutomationResult(
            success=False, action="select_vendor",
            model=model, record_id=record_id,
            reasoning="Failed to optimize vendor selection",
        )

    def _create_purchase_orders(self, po_data: dict):
        """Create actual purchase orders in Odoo from AI suggestions."""
        lines_by_vendor: dict[int, list] = {}
        for line in po_data.get("lines", []):
            vendor_id = line.get("vendor_id", 0)
            if vendor_id:
                lines_by_vendor.setdefault(vendor_id, []).append(line)

        for vendor_id, lines in lines_by_vendor.items():
            try:
                po_id = self.create_record("purchase.order", {
                    "partner_id": vendor_id,
                })
                for line in lines:
                    self.create_record("purchase.order.line", {
                        "order_id": po_id,
                        "product_id": line["product_id"],
                        "product_qty": line["quantity"],
                        "price_unit": line.get("estimated_price", 0),
                    })
                logger.info(
                    "auto_po_created",
                    po_id=po_id,
                    vendor_id=vendor_id,
                    lines=len(lines),
                )
            except Exception as exc:
                logger.error("auto_po_creation_failed", vendor_id=vendor_id, error=str(exc))

    def action_match_bills(self, model: str, record_id: int) -> AutomationResult:
        """Match a vendor bill to purchase orders."""
        bill = self.fetch_record_context("account.move", record_id)
        if not bill or bill.get("move_type") not in ("in_invoice", "in_refund"):
            return AutomationResult(
                success=False, action="match_bills",
                model=model, record_id=record_id,
                reasoning="Not a vendor bill",
            )

        partner_id = bill.get("partner_id")
        if isinstance(partner_id, (list, tuple)):
            partner_id = partner_id[0]

        open_pos = self.fetch_related_records(
            "purchase.order",
            [
                ("partner_id", "=", partner_id),
                ("state", "=", "purchase"),
                ("invoice_status", "in", ["to invoice", "no"]),
            ],
            fields=["name", "amount_total", "date_order", "date_planned"],
            limit=20,
        )

        user_msg = f"""Match this vendor bill to purchase orders:

Bill:
- Vendor: {bill.get('partner_id', 'N/A')}
- Amount: {bill.get('amount_total', 0)}
- Date: {bill.get('invoice_date', 'N/A')}
- Reference: {bill.get('ref', 'N/A')}

Open purchase orders from this vendor:
{json.dumps(open_pos, indent=2, default=str)}

Match based on amount, date proximity, and reference patterns.
Flag any discrepancies between bill amount and PO amount."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, BILL_MATCH_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="match_bills",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=bool(tool_result.get("discrepancies")),
            )

        return AutomationResult(
            success=False, action="match_bills",
            model=model, record_id=record_id,
            reasoning="Failed to match vendor bill",
        )
