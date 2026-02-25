"""
Natural language chat interface — talk to your ERP in plain English.
Ask questions, trigger actions, and get insights without navigating menus.
"""

import json
from typing import Any

import structlog

from app.odoo_client import get_odoo_client
from app.claude_client import get_claude_client
from app.config import get_settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an AI ERP assistant connected to a live Odoo Enterprise system.
You help users interact with their business data using natural language.

You have tools to:
1. Search and read any data in Odoo (CRM leads, invoices, stock, HR, projects, etc.)
2. Perform actions (create records, update fields, confirm orders, etc.)
3. Generate reports and summaries
4. Trigger automations

IMPORTANT RULES:
- Always confirm destructive actions before executing (deleting, confirming large orders, etc.)
- When showing data, format it clearly and concisely
- If unsure about a model or field name, search for it first
- Explain what you're doing in simple business terms, not technical jargon
- For write/create operations, always show what you're about to do and ask for confirmation
- Currency amounts should be formatted properly
- Dates should be human-readable"""

CHAT_TOOLS = [
    {
        "name": "odoo_search",
        "description": "Search for records in any Odoo model",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Odoo model (e.g. crm.lead, sale.order, account.move)"},
                "domain": {
                    "type": "array",
                    "description": "Odoo search domain filter",
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fields to return",
                },
                "limit": {"type": "integer", "description": "Max results"},
                "order": {"type": "string", "description": "Sort order"},
            },
            "required": ["model", "domain", "fields"],
        },
    },
    {
        "name": "odoo_read",
        "description": "Read a specific record by ID",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "record_id": {"type": "integer"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["model", "record_id"],
        },
    },
    {
        "name": "odoo_write",
        "description": "Update a record (requires user confirmation)",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "record_id": {"type": "integer"},
                "values": {"type": "object"},
                "description": {"type": "string", "description": "Human-readable description of the change"},
            },
            "required": ["model", "record_id", "values", "description"],
        },
    },
    {
        "name": "odoo_create",
        "description": "Create a new record (requires user confirmation)",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "values": {"type": "object"},
                "description": {"type": "string", "description": "Human-readable description"},
            },
            "required": ["model", "values", "description"],
        },
    },
    {
        "name": "odoo_action",
        "description": "Execute a method on a record (e.g. confirm order, validate invoice)",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "record_id": {"type": "integer"},
                "method": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["model", "record_id", "method", "description"],
        },
    },
    {
        "name": "odoo_count",
        "description": "Count records matching a domain",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {"type": "array"},
            },
            "required": ["model", "domain"],
        },
    },
    {
        "name": "generate_report",
        "description": "Generate a summary report from queried data",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string", "description": "Formatted report content"},
                "highlights": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "content"],
        },
    },
]


class ChatSession:
    def __init__(self):
        self.odoo = get_odoo_client()
        self.claude = get_claude_client()
        self.messages: list[dict] = []
        self.pending_actions: list[dict] = []

    def send_message(self, user_message: str) -> dict[str, Any]:
        """Process a user message and return AI response with any actions taken."""
        self.messages.append({"role": "user", "content": user_message})

        result = self.claude.analyze_with_history(
            system_prompt=SYSTEM_PROMPT,
            messages=self.messages,
            tools=CHAT_TOOLS,
        )

        response_text = result.get("text", "")
        actions_taken = []
        needs_confirmation = False
        confirmation_details = []

        for tool_call in result.get("tool_calls", []):
            tool_name = tool_call["name"]
            tool_input = tool_call["input"]

            if tool_name in ("odoo_write", "odoo_create", "odoo_action"):
                needs_confirmation = True
                confirmation_details.append({
                    "action": tool_name,
                    "details": tool_input,
                    "tool_call_id": tool_call["id"],
                })
            else:
                action_result = self._execute_tool(tool_name, tool_input)
                actions_taken.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "result": action_result,
                })

                self.messages.append({
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": tool_call["id"],
                                 "name": tool_name, "input": tool_input}],
                })
                self.messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tool_call["id"],
                                 "content": json.dumps(action_result, default=str)}],
                })

        if actions_taken and not needs_confirmation:
            followup = self.claude.analyze_with_history(
                system_prompt=SYSTEM_PROMPT,
                messages=self.messages,
                tools=CHAT_TOOLS,
            )
            response_text = followup.get("text", response_text)

        if needs_confirmation:
            self.pending_actions = confirmation_details

        self.messages.append({"role": "assistant", "content": response_text})

        return {
            "response": response_text,
            "actions_taken": actions_taken,
            "needs_confirmation": needs_confirmation,
            "confirmation_details": confirmation_details,
        }

    def confirm_actions(self, confirmed: bool) -> dict[str, Any]:
        """Confirm or reject pending write/create/action operations."""
        results = []

        if confirmed and self.pending_actions:
            for action in self.pending_actions:
                tool_name = action["action"]
                tool_input = action["details"]
                result = self._execute_tool(tool_name, tool_input)
                results.append({
                    "tool": tool_name,
                    "result": result,
                    "description": tool_input.get("description", ""),
                })

            response = f"Done! Executed {len(results)} action(s):\n"
            for r in results:
                response += f"- {r['description']}\n"
        else:
            response = "Actions cancelled. No changes were made."

        self.pending_actions = []
        return {"response": response, "results": results}

    def _execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Execute an Odoo tool call and return the result."""
        try:
            if tool_name == "odoo_search":
                return self.odoo.search_read(
                    tool_input["model"],
                    tool_input.get("domain", []),
                    fields=tool_input.get("fields"),
                    limit=tool_input.get("limit", 20),
                    order=tool_input.get("order"),
                )
            elif tool_name == "odoo_read":
                return self.odoo.get_record(
                    tool_input["model"],
                    tool_input["record_id"],
                    tool_input.get("fields"),
                )
            elif tool_name == "odoo_write":
                self.odoo.write(
                    tool_input["model"],
                    [tool_input["record_id"]],
                    tool_input["values"],
                )
                return {"success": True, "description": tool_input.get("description")}
            elif tool_name == "odoo_create":
                record_id = self.odoo.create(
                    tool_input["model"],
                    tool_input["values"],
                )
                return {"success": True, "record_id": record_id}
            elif tool_name == "odoo_action":
                self.odoo.execute_method(
                    tool_input["model"],
                    tool_input["method"],
                    [tool_input["record_id"]],
                )
                return {"success": True}
            elif tool_name == "odoo_count":
                count = self.odoo.search_count(
                    tool_input["model"],
                    tool_input.get("domain", []),
                )
                return {"count": count}
            elif tool_name == "generate_report":
                return tool_input
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as exc:
            logger.error("chat_tool_error", tool=tool_name, error=str(exc))
            return {"error": str(exc)}


_sessions: dict[str, ChatSession] = {}


def get_or_create_session(session_id: str) -> ChatSession:
    if session_id not in _sessions:
        _sessions[session_id] = ChatSession()
    return _sessions[session_id]
