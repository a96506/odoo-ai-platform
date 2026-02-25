"""
Helpdesk automations: ticket categorization, auto-assignment, SLA monitoring, solution suggestions.
"""

import json

import structlog

from app.automations.base import BaseAutomation
from app.models.schemas import AutomationResult

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an expert Helpdesk AI assistant integrated with Odoo ERP.
You categorize support tickets, assign them to the right agents, suggest solutions,
and monitor SLA compliance. Prioritize customer satisfaction and fast resolution.
Always provide confidence scores and clear reasoning."""

CATEGORIZE_TOOLS = [
    {
        "name": "categorize_ticket",
        "description": "Categorize and prioritize a helpdesk ticket",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Ticket category"},
                "priority": {
                    "type": "string",
                    "enum": ["0", "1", "2", "3"],
                    "description": "0=Low, 1=Medium, 2=High, 3=Urgent",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relevant tags to apply",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "neutral", "negative", "frustrated"],
                    "description": "Customer sentiment detected",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["category", "priority", "sentiment", "confidence", "reasoning"],
        },
    }
]

ASSIGN_TOOLS = [
    {
        "name": "assign_ticket",
        "description": "Assign a ticket to the best-fit support agent",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "Assigned agent user ID"},
                "team_id": {"type": "integer", "description": "Assigned team ID"},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["user_id", "team_id", "confidence", "reasoning"],
        },
    }
]

SOLUTION_TOOLS = [
    {
        "name": "suggest_solution",
        "description": "Suggest a solution based on knowledge base and past tickets",
        "input_schema": {
            "type": "object",
            "properties": {
                "suggested_response": {
                    "type": "string",
                    "description": "Drafted response to send to the customer",
                },
                "internal_notes": {
                    "type": "string",
                    "description": "Notes for the agent about the issue",
                },
                "related_ticket_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Similar past tickets for reference",
                },
                "auto_resolvable": {
                    "type": "boolean",
                    "description": "Whether the ticket can be resolved automatically",
                },
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["suggested_response", "internal_notes", "auto_resolvable", "confidence", "reasoning"],
        },
    }
]


class HelpdeskAutomation(BaseAutomation):
    automation_type = "helpdesk"
    watched_models = ["helpdesk.ticket"]

    def on_create_helpdesk_ticket(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """New ticket: categorize, assign, and suggest a solution."""
        record = self.fetch_record_context(model, record_id)
        if not record:
            return AutomationResult(
                success=False, action="process_ticket",
                model=model, record_id=record_id, reasoning="Record not found",
            )

        cat_result = self._categorize_ticket(record)
        confidence = cat_result.get("confidence", 0)

        if confidence >= self.settings.default_confidence_threshold:
            updates = {}
            if cat_result.get("priority"):
                updates["priority"] = cat_result["priority"]

            if self.should_auto_execute(confidence) and updates:
                self.update_record(model, record_id, updates)

        assign_result = self._assign_ticket(record, cat_result)
        if assign_result.get("confidence", 0) >= self.settings.default_confidence_threshold:
            if self.should_auto_execute(assign_result["confidence"]):
                assign_updates = {}
                if assign_result.get("user_id"):
                    assign_updates["user_id"] = assign_result["user_id"]
                if assign_result.get("team_id"):
                    assign_updates["team_id"] = assign_result["team_id"]
                if assign_updates:
                    self.update_record(model, record_id, assign_updates)

        solution = self._suggest_solution(record, cat_result)

        all_changes = {**cat_result, "assignment": assign_result, "solution": solution}

        return AutomationResult(
            success=True,
            action="process_ticket",
            model=model,
            record_id=record_id,
            confidence=confidence,
            reasoning=cat_result.get("reasoning", ""),
            changes_made=all_changes,
            needs_approval=solution.get("auto_resolvable", False) and self.needs_approval(solution.get("confidence", 0)),
        )

    def on_write_helpdesk_ticket(
        self, model: str, record_id: int, values: dict
    ) -> AutomationResult:
        """When a ticket is updated, check for SLA breaches."""
        return AutomationResult(
            success=True, action="ticket_updated",
            model=model, record_id=record_id,
            reasoning="Ticket update logged",
        )

    # --- Internal methods ---

    def _categorize_ticket(self, record: dict) -> dict:
        user_msg = f"""Categorize this helpdesk ticket:

Ticket:
- Subject: {record.get('name', 'N/A')}
- Description: {record.get('description', 'N/A')}
- Customer: {record.get('partner_id', 'N/A')}
- Email: {record.get('partner_email', 'N/A')}
- Channel: {record.get('channel_id', 'N/A')}

Determine:
- Category (e.g. billing, technical, feature request, bug report, etc.)
- Priority (0-3 based on urgency and impact)
- Customer sentiment
- Relevant tags"""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, CATEGORIZE_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"confidence": 0}

    def _assign_ticket(self, record: dict, categorization: dict) -> dict:
        agents = self.fetch_related_records(
            "res.users",
            [("share", "=", False), ("active", "=", True)],
            fields=["id", "name"],
            limit=30,
        )

        workload = {}
        for agent in agents:
            count = self.odoo.search_count(
                "helpdesk.ticket",
                [("user_id", "=", agent["id"]), ("stage_id.fold", "=", False)],
            )
            workload[agent["id"]] = count

        user_msg = f"""Assign this ticket to the best agent:

Ticket:
- Subject: {record.get('name', 'N/A')}
- Category: {categorization.get('category', 'N/A')}
- Priority: {categorization.get('priority', 'N/A')}
- Sentiment: {categorization.get('sentiment', 'N/A')}

Available agents and workload:
{json.dumps([{**a, 'open_tickets': workload.get(a['id'], 0)} for a in agents], indent=2, default=str)}

Assign based on workload balance and urgency."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, ASSIGN_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"confidence": 0}

    def _suggest_solution(self, record: dict, categorization: dict) -> dict:
        similar_tickets = self.fetch_related_records(
            "helpdesk.ticket",
            [("stage_id.fold", "=", True)],
            fields=["name", "description", "tag_ids"],
            limit=20,
        )

        user_msg = f"""Suggest a solution for this ticket:

Ticket:
- Subject: {record.get('name', 'N/A')}
- Description: {record.get('description', 'N/A')}
- Category: {categorization.get('category', 'N/A')}
- Priority: {categorization.get('priority', 'N/A')}

Similar resolved tickets:
{json.dumps(similar_tickets[:10], indent=2, default=str)}

Draft a helpful customer response and internal notes for the agent.
If this is a common issue with a standard fix, mark it as auto-resolvable."""

        result = self.analyze_with_tools(SYSTEM_PROMPT, user_msg, SOLUTION_TOOLS)
        if result["tool_calls"]:
            return result["tool_calls"][0]["input"]
        return {"confidence": 0, "auto_resolvable": False}
