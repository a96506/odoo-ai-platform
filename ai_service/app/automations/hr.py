"""
HR automations: leave approval, expense processing, attendance anomaly detection.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert HR AI assistant integrated with Odoo ERP.
You help automate routine HR tasks while ensuring compliance with company policies.
Always err on the side of caution for approvals — flag edge cases for human review.
Provide confidence scores and clear reasoning for every decision."""

LEAVE_TOOLS = [
    {
        "name": "evaluate_leave_request",
        "description": "Evaluate a leave request against company policy",
        "input_schema": {
            "type": "object",
            "properties": {
                "recommendation": {
                    "type": "string",
                    "enum": ["approve", "reject", "escalate"],
                    "description": "Recommended action",
                },
                "policy_compliant": {"type": "boolean"},
                "remaining_balance": {
                    "type": "number",
                    "description": "Remaining leave balance after approval",
                },
                "conflicts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any scheduling conflicts found",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["recommendation", "policy_compliant", "conflicts", "confidence", "reasoning"],
        },
    }
]

EXPENSE_TOOLS = [
    {
        "name": "process_expense",
        "description": "Categorize and validate an expense report",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Expense category"},
                "within_policy": {"type": "boolean"},
                "flags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Policy violations or concerns",
                },
                "suggested_account_id": {
                    "type": "integer",
                    "description": "Suggested accounting account ID",
                },
                "recommendation": {
                    "type": "string",
                    "enum": ["approve", "reject", "escalate"],
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["category", "within_policy", "flags", "recommendation", "confidence", "reasoning"],
        },
    }
]

ATTENDANCE_TOOLS = [
    {
        "name": "detect_attendance_anomaly",
        "description": "Detect anomalies in employee attendance patterns",
        "input_schema": {
            "type": "object",
            "properties": {
                "anomalies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "employee_name": {"type": "string"},
                            "anomaly_type": {"type": "string", "enum": [
                                "excessive_overtime", "frequent_late", "unusual_pattern",
                                "missing_checkout", "weekend_work",
                            ]},
                            "details": {"type": "string"},
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


class HRAutomation(BaseAutomation):
    automation_type = "hr"
    watched_models = ["hr.leave", "hr.expense"]

    def on_create_hr_leave(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a leave request is submitted, evaluate it against policy."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="evaluate_leave",
                model=model, record_id=record_id, reasoning="Record not found",
            )
        return self._evaluate_leave(model, record_id, record)

    def on_create_hr_expense(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a new expense is submitted, categorize and validate."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="process_expense",
                model=model, record_id=record_id, reasoning="Record not found",
            )
        return self._process_expense(model, record_id, record)

    # --- Internal methods ---

    def _evaluate_leave(
        self, model: str, record_id: int, record: dict
    ) -> AutomationResult:
        employee_id = record.get("employee_id")
        if isinstance(employee_id, (list, tuple)):
            employee_id = employee_id[0]

        existing_leaves = self.fetch_related_records(
            "hr.leave",
            [
                ("employee_id", "=", employee_id),
                ("state", "in", ["confirm", "validate"]),
                ("id", "!=", record_id),
            ],
            fields=["date_from", "date_to", "number_of_days", "holiday_status_id", "state"],
            limit=20,
        )

        team_leaves = self.fetch_related_records(
            "hr.leave",
            [
                ("state", "in", ["confirm", "validate"]),
                ("date_from", "<=", record.get("date_to", "")),
                ("date_to", ">=", record.get("date_from", "")),
            ],
            fields=["employee_id", "date_from", "date_to"],
            limit=30,
        )

        allocations = self.fetch_related_records(
            "hr.leave.allocation",
            [("employee_id", "=", employee_id), ("state", "=", "validate")],
            fields=["holiday_status_id", "number_of_days", "max_leaves", "leaves_taken"],
            limit=10,
        )

        user_msg = f"""Evaluate this leave request:

Request:
- Employee: {record.get('employee_id', 'N/A')}
- Leave Type: {record.get('holiday_status_id', 'N/A')}
- From: {record.get('date_from', 'N/A')}
- To: {record.get('date_to', 'N/A')}
- Days: {record.get('number_of_days', 0)}
- Reason: {record.get('name', 'N/A')}

Employee's existing leaves this year:
{json.dumps(existing_leaves, indent=2, default=str)}

Employee's leave allocations:
{json.dumps(allocations, indent=2, default=str)}

Team members on leave during same period:
{json.dumps(team_leaves, indent=2, default=str)}

Evaluate:
- Does the employee have sufficient leave balance?
- Are there scheduling conflicts with the team?
- Is this a routine request or does it need manager attention?
- Simple 1-2 day requests with balance available should be approved
- Long leaves or those causing team coverage gaps should be escalated"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, LEAVE_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            confidence = tool_result.get("confidence", 0)
            recommendation = tool_result.get("recommendation", "escalate")

            if recommendation == "approve" and self.should_auto_execute(confidence):
                self.update_record(model, record_id, {"state": "validate"})
                return AutomationResult(
                    success=True,
                    action="approve_leave",
                    model=model,
                    record_id=record_id,
                    confidence=confidence,
                    reasoning=tool_result.get("reasoning", ""),
                    changes_made=tool_result,
                    needs_approval=False,
                )

            return AutomationResult(
                success=True,
                action="evaluate_leave",
                model=model,
                record_id=record_id,
                confidence=confidence,
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=recommendation != "reject",
            )

        return AutomationResult(
            success=False, action="evaluate_leave",
            model=model, record_id=record_id,
            reasoning="Leave evaluation produced no result",
        )

    def _process_expense(
        self, model: str, record_id: int, record: dict
    ) -> AutomationResult:
        employee_id = record.get("employee_id")
        if isinstance(employee_id, (list, tuple)):
            employee_id = employee_id[0]

        past_expenses = self.fetch_related_records(
            "hr.expense",
            [("employee_id", "=", employee_id), ("state", "in", ["approved", "done"])],
            fields=["name", "total_amount", "product_id", "date", "description"],
            limit=20,
        )

        user_msg = f"""Categorize and validate this expense:

Expense:
- Description: {record.get('name', 'N/A')}
- Amount: {record.get('total_amount', 0)} {record.get('currency_id', '')}
- Date: {record.get('date', 'N/A')}
- Category: {record.get('product_id', 'N/A')}
- Notes: {record.get('description', 'N/A')}
- Reference: {record.get('reference', 'N/A')}

Employee's past expenses:
{json.dumps(past_expenses[:10], indent=2, default=str)}

Validate:
- Is the amount reasonable for the category?
- Does it match typical expense patterns for this employee?
- Are there any policy red flags (very large amount, vague description, etc.)?
- Recommend approve for routine expenses, escalate for unusual ones"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, EXPENSE_TOOLS)

        if result["tool_calls"]:
            tool_result = result["tool_calls"][0]["input"]
            confidence = tool_result.get("confidence", 0)

            return AutomationResult(
                success=True,
                action="process_expense",
                model=model,
                record_id=record_id,
                confidence=confidence,
                reasoning=tool_result.get("reasoning", ""),
                changes_made=tool_result,
                needs_approval=tool_result.get("recommendation") != "approve"
                or not self.should_auto_execute(confidence),
            )

        return AutomationResult(
            success=False, action="process_expense",
            model=model, record_id=record_id,
            reasoning="Expense processing produced no result",
        )
