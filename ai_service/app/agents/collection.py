"""
CollectionAgent — multi-step workflow for overdue invoice collection.

Pipeline: assess customer -> determine strategy -> draft message ->
          send via channel -> track response -> escalate if needed ->
          update credit score
"""

from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents import register_agent
from app.agents.base_agent import AgentState, BaseAgent

logger = structlog.get_logger()


class CollectionState(TypedDict, total=False):
    # Base fields
    run_id: int
    step_count: int
    token_count: int
    error: str | None
    needs_suspension: bool
    suspension_reason: str | None
    current_step: str

    # Domain fields
    invoice_id: int
    partner_id: int
    invoice_data: dict[str, Any]
    customer_profile: dict[str, Any]
    overdue_days: int
    amount_due: float
    collection_strategy: str  # "gentle_reminder" | "firm_notice" | "final_demand" | "escalate"
    message_draft: str
    channel: str  # "email" | "slack"
    message_sent: bool
    response_received: bool
    escalation_needed: bool
    credit_score_impact: float


class CollectionAgent(BaseAgent):
    agent_type = "collection"
    description = "Overdue invoice collection: assess → strategize → contact → track → escalate"

    def get_state_schema(self) -> type:
        return CollectionState

    def build_graph(self) -> StateGraph:
        graph = StateGraph(CollectionState)

        graph.add_node("assess_customer", self._assess_customer)
        graph.add_node("determine_strategy", self._determine_strategy)
        graph.add_node("draft_message", self._draft_message)
        graph.add_node("send_message", self._send_message)
        graph.add_node("check_escalation", self._check_escalation)
        graph.add_node("escalate", self._escalate)
        graph.add_node("update_credit_score", self._update_credit_score)

        graph.add_edge(START, "assess_customer")
        graph.add_edge("assess_customer", "determine_strategy")
        graph.add_conditional_edges(
            "determine_strategy",
            self._route_strategy,
            {
                "contact": "draft_message",
                "escalate_immediately": "escalate",
            },
        )
        graph.add_edge("draft_message", "send_message")
        graph.add_edge("send_message", "check_escalation")
        graph.add_conditional_edges(
            "check_escalation",
            self._route_escalation,
            {"escalate": "escalate", "done": "update_credit_score"},
        )
        graph.add_edge("escalate", "update_credit_score")
        graph.add_edge("update_credit_score", END)

        return graph

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    def _assess_customer(self, state: CollectionState) -> dict:
        invoice_id = state.get("invoice_id")
        if not invoice_id:
            return {"error": "No invoice_id provided"}

        invoice = self.fetch_record(
            "account.move", invoice_id,
            fields=["partner_id", "amount_residual", "invoice_date_due",
                     "state", "payment_state", "name"],
        )
        if not invoice:
            return {"error": f"Invoice {invoice_id} not found"}

        partner_info = invoice.get("partner_id")
        partner_id = partner_info[0] if isinstance(partner_info, (list, tuple)) else partner_info

        customer = self.fetch_record(
            "res.partner", partner_id,
            fields=["name", "email", "phone", "customer_rank", "credit_limit",
                     "total_due", "total_overdue"],
        )

        from datetime import date, datetime
        due_date_str = invoice.get("invoice_date_due", "")
        overdue_days = 0
        if due_date_str:
            try:
                if isinstance(due_date_str, str):
                    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                else:
                    due_date = due_date_str
                overdue_days = (date.today() - due_date).days
            except (ValueError, TypeError):
                overdue_days = 0

        return {
            "invoice_data": invoice,
            "customer_profile": customer or {},
            "partner_id": partner_id,
            "overdue_days": max(overdue_days, 0),
            "amount_due": invoice.get("amount_residual", 0),
        }

    def _determine_strategy(self, state: CollectionState) -> dict:
        overdue_days = state.get("overdue_days", 0)
        amount_due = state.get("amount_due", 0)
        customer = state.get("customer_profile", {})

        total_overdue = customer.get("total_overdue", 0)

        if overdue_days <= 7:
            strategy = "gentle_reminder"
        elif overdue_days <= 30:
            strategy = "firm_notice"
        elif overdue_days <= 60:
            strategy = "final_demand"
        else:
            strategy = "escalate"

        if amount_due > 50000 and overdue_days > 14:
            strategy = "escalate"

        return {"collection_strategy": strategy}

    def _draft_message(self, state: CollectionState) -> dict:
        strategy = state.get("collection_strategy", "gentle_reminder")
        invoice = state.get("invoice_data", {})
        customer = state.get("customer_profile", {})
        amount = state.get("amount_due", 0)
        overdue_days = state.get("overdue_days", 0)

        try:
            result = self.analyze_with_tools(
                system_prompt=(
                    "You are a professional accounts receivable specialist. "
                    "Draft a collection message appropriate to the strategy level. "
                    "Be professional, clear, and include the invoice details."
                ),
                user_message=(
                    f"Strategy: {strategy}\n"
                    f"Customer: {customer.get('name', 'Unknown')}\n"
                    f"Invoice: {invoice.get('name', 'N/A')}\n"
                    f"Amount due: {amount:.2f}\n"
                    f"Days overdue: {overdue_days}\n"
                ),
                tools=[{
                    "name": "draft_collection_message",
                    "description": "Draft a collection message",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                            "tone": {"type": "string", "enum": ["friendly", "firm", "urgent", "legal"]},
                        },
                        "required": ["subject", "body", "tone"],
                    },
                }],
                state=state,
            )
            draft = result.get("tool_input", {})
            message = draft.get("body", f"Payment reminder for invoice {invoice.get('name', '')}: {amount:.2f} overdue by {overdue_days} days.")
        except Exception:
            message = (
                f"Dear Customer,\n\n"
                f"This is a reminder that invoice {invoice.get('name', '')} "
                f"for {amount:.2f} is {overdue_days} days overdue. "
                f"Please arrange payment at your earliest convenience.\n\n"
                f"Best regards,\nAccounts Receivable"
            )

        channel = "email"
        if self.settings.slack_enabled:
            channel = "slack"

        return {"message_draft": message, "channel": channel}

    def _send_message(self, state: CollectionState) -> dict:
        channel = state.get("channel", "email")
        customer = state.get("customer_profile", {})
        message = state.get("message_draft", "")
        invoice = state.get("invoice_data", {})

        recipient = customer.get("email", "")
        if channel == "slack":
            recipient = self.settings.slack_default_channel

        subject = f"Payment Reminder: {invoice.get('name', 'Invoice')}"
        sent = self.notify(channel, recipient, subject, message)

        return {"message_sent": sent}

    def _check_escalation(self, state: CollectionState) -> dict:
        strategy = state.get("collection_strategy", "")
        sent = state.get("message_sent", False)
        overdue_days = state.get("overdue_days", 0)

        escalate = (
            strategy in ("final_demand", "escalate")
            or (not sent and overdue_days > 30)
        )
        return {"escalation_needed": escalate}

    def _escalate(self, state: CollectionState) -> dict:
        invoice = state.get("invoice_data", {})
        customer = state.get("customer_profile", {})
        amount = state.get("amount_due", 0)

        self.notify(
            "slack", self.settings.slack_default_channel,
            f"ESCALATION: Overdue Invoice {invoice.get('name', '')}",
            f"Customer {customer.get('name', 'Unknown')} owes {amount:.2f}, "
            f"{state.get('overdue_days', 0)} days overdue. Requires management attention.",
        )
        return {}

    def _update_credit_score(self, state: CollectionState) -> dict:
        overdue_days = state.get("overdue_days", 0)
        if overdue_days > 60:
            impact = -15.0
        elif overdue_days > 30:
            impact = -8.0
        elif overdue_days > 14:
            impact = -3.0
        else:
            impact = -1.0

        return {"credit_score_impact": impact}

    # ------------------------------------------------------------------
    # Routing functions
    # ------------------------------------------------------------------

    def _route_strategy(self, state: CollectionState) -> str:
        strategy = state.get("collection_strategy", "")
        if strategy == "escalate":
            return "escalate_immediately"
        return "contact"

    def _route_escalation(self, state: CollectionState) -> str:
        return "escalate" if state.get("escalation_needed") else "done"


register_agent(CollectionAgent)
