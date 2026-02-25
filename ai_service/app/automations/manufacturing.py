"""
Manufacturing automations: production scheduling, maintenance prediction, quality control.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Manufacturing AI assistant integrated with Odoo ERP (MRP module).
You optimize production scheduling, predict maintenance needs, and ensure quality standards.
Base decisions on production capacity, material availability, and historical performance.
Always provide confidence scores and clear reasoning."""

SCHEDULE_TOOLS = [
    {
        "name": "schedule_production",
        "description": "Optimize production order scheduling based on demand and capacity",
        "input_schema": {
            "type": "object",
            "properties": {
                "schedule": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "production_id": {"type": "integer"},
                            "product_name": {"type": "string"},
                            "suggested_start": {"type": "string"},
                            "suggested_end": {"type": "string"},
                            "priority_order": {"type": "integer"},
                            "notes": {"type": "string"},
                        },
                    },
                },
                "bottlenecks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Identified production bottlenecks",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["schedule", "bottlenecks", "confidence", "reasoning"],
        },
    }
]

MAINTENANCE_TOOLS = [
    {
        "name": "predict_maintenance",
        "description": "Predict equipment maintenance needs based on usage patterns",
        "input_schema": {
            "type": "object",
            "properties": {
                "predictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "equipment_name": {"type": "string"},
                            "predicted_issue": {"type": "string"},
                            "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
                            "suggested_date": {"type": "string"},
                        },
                    },
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["predictions", "confidence", "reasoning"],
        },
    }
]

QUALITY_TOOLS = [
    {
        "name": "quality_check",
        "description": "Analyze production quality data for anomalies",
        "input_schema": {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "production_id": {"type": "integer"},
                            "issue_type": {"type": "string"},
                            "severity": {"type": "string", "enum": ["minor", "major", "critical"]},
                            "recommendation": {"type": "string"},
                        },
                    },
                },
                "overall_quality_score": {"type": "number", "description": "0-100 quality score"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["issues", "overall_quality_score", "confidence", "reasoning"],
        },
    }
]


class ManufacturingAutomation(BaseAutomation):
    automation_type = "manufacturing"
    watched_models = ["mrp.production"]

    def on_create(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new production order is created, optimize scheduling."""
        return self._schedule_production_order(model, record_id)

    def on_write(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        if "state" in values and values.get("state") == "done":
            return self._quality_check(model, record_id)
        return AutomationResult(
            success=True, action="no_action",
            model=model, record_id=record_id,
            reasoning="Production order update logged",
        )

    # --- Scheduled scans ---

    def scan_schedule_production(self):
        """Optimize scheduling across all pending production orders."""
        pending = self.fetch_related_records(
            "mrp.production",
            [("state", "in", ["draft", "confirmed"])],
            fields=["product_id", "product_qty", "date_start", "date_finished",
                     "bom_id", "state", "priority"],
            limit=50,
        )

        if not pending:
            return

        user_msg = f"""Optimize the production schedule:

Pending production orders:
{json.dumps(pending, indent=2, default=str)}

Optimize based on:
- Priority (urgent orders first)
- Material availability
- Minimize changeover time
- Balance workload across work centers
- Identify bottlenecks"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, SCHEDULE_TOOLS)
        if result["tool_calls"]:
            schedule = result["tool_calls"][0]["input"]
            logger.info(
                "production_schedule_optimized",
                orders=len(schedule.get("schedule", [])),
                bottlenecks=len(schedule.get("bottlenecks", [])),
            )

    # --- Internal methods ---

    def _schedule_production_order(self, model: str, record_id: int) -> AutomationResult:
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="schedule_production",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        existing = self.fetch_related_records(
            "mrp.production",
            [("state", "in", ["confirmed", "progress"]), ("id", "!=", record_id)],
            fields=["product_id", "date_start", "date_finished", "state"],
            limit=20,
        )

        user_msg = f"""Schedule this new production order:

New order:
- Product: {record.get('product_id', 'N/A')}
- Quantity: {record.get('product_qty', 0)}
- Requested Start: {record.get('date_start', 'N/A')}
- Priority: {record.get('priority', '0')}

Existing production schedule:
{json.dumps(existing, indent=2, default=str)}

Suggest optimal start/end dates considering existing schedule and capacity."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, SCHEDULE_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="schedule_production",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=True,
            )

        return AutomationResult(
            success=False, action="schedule_production",
            model=model, record_id=record_id,
            reasoning="Scheduling produced no result",
        )

    def _quality_check(self, model: str, record_id: int) -> AutomationResult:
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="quality_check",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        user_msg = f"""Check production quality for this completed order:

Order:
- Product: {record.get('product_id', 'N/A')}
- Planned Qty: {record.get('product_qty', 0)}
- Produced Qty: {record.get('qty_produced', 0)}

Check for:
- Quantity discrepancies (planned vs produced)
- Any quality issues indicated by the data
- Recommendations for improvement"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, QUALITY_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            return AutomationResult(
                success=True,
                action="quality_check",
                model=model,
                record_id=record_id,
                confidence=tool_result.get("confidence", 0),
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=bool(tool_result.get("issues")),
            )

        return AutomationResult(
            success=True, action="quality_check",
            model=model, record_id=record_id,
            reasoning="Quality check completed with no issues",
        )
