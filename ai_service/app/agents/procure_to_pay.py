"""
ProcureToPayAgent — multi-step workflow for vendor invoice processing.

Pipeline: extract document -> match PO -> validate amounts ->
          check goods receipt -> create draft bill -> route for approval ->
          post bill -> update vendor score -> notify stakeholders
"""

from __future__ import annotations

from typing import Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents import register_agent
from app.agents.base_agent import AgentState, BaseAgent

logger = structlog.get_logger()


class P2PState(TypedDict, total=False):
    # Base fields
    run_id: int
    step_count: int
    token_count: int
    error: str | None
    needs_suspension: bool
    suspension_reason: str | None
    current_step: str

    # Domain fields
    document_id: int | None
    extracted_data: dict[str, Any]
    matched_po: dict[str, Any] | None
    po_match_confidence: float
    discrepancies: list[dict[str, Any]]
    goods_received: bool
    bill_id: int | None
    approval_decision: str  # "auto_approve" | "needs_approval" | "escalate"
    overall_confidence: float
    notifications_sent: list[str]
    vendor_id: int | None
    vendor_score_delta: float


class ProcureToPayAgent(BaseAgent):
    agent_type = "procure_to_pay"
    description = "Full procure-to-pay: invoice → PO match → bill → approve → pay"

    def get_state_schema(self) -> type:
        return P2PState

    def build_graph(self) -> StateGraph:
        graph = StateGraph(P2PState)

        graph.add_node("extract_document", self._extract_document)
        graph.add_node("match_purchase_order", self._match_purchase_order)
        graph.add_node("validate_amounts", self._validate_amounts)
        graph.add_node("check_goods_receipt", self._check_goods_receipt)
        graph.add_node("create_draft_bill", self._create_draft_bill)
        graph.add_node("route_for_approval", self._route_for_approval)
        graph.add_node("suspend_for_approval", self._suspend_for_approval)
        graph.add_node("post_bill", self._post_bill)
        graph.add_node("update_vendor_score", self._update_vendor_score)
        graph.add_node("notify_stakeholders", self._notify_stakeholders)

        graph.add_edge(START, "extract_document")
        graph.add_conditional_edges(
            "extract_document",
            self._route_after_extraction,
            {"success": "match_purchase_order", "failure": "notify_stakeholders"},
        )
        graph.add_conditional_edges(
            "match_purchase_order",
            self._route_after_po_match,
            {"found": "validate_amounts", "not_found": "notify_stakeholders"},
        )
        graph.add_conditional_edges(
            "validate_amounts",
            self._route_after_validation,
            {"match": "check_goods_receipt", "discrepancy": "notify_stakeholders"},
        )
        graph.add_conditional_edges(
            "check_goods_receipt",
            self._route_after_receipt_check,
            {"received": "create_draft_bill", "not_received": "notify_stakeholders"},
        )
        graph.add_edge("create_draft_bill", "route_for_approval")
        graph.add_conditional_edges(
            "route_for_approval",
            self._route_approval_decision,
            {
                "auto_approve": "post_bill",
                "needs_approval": "suspend_for_approval",
                "escalate": "notify_stakeholders",
            },
        )
        graph.add_edge("suspend_for_approval", END)
        graph.add_edge("post_bill", "update_vendor_score")
        graph.add_edge("update_vendor_score", "notify_stakeholders")
        graph.add_edge("notify_stakeholders", END)

        return graph

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    def _extract_document(self, state: P2PState) -> dict:
        document_id = state.get("document_id")
        extracted = state.get("extracted_data", {})

        if not extracted and document_id:
            try:
                result = self.analyze_with_tools(
                    system_prompt=(
                        "You are an invoice data extraction assistant. "
                        "Extract vendor name, invoice number, date, line items, "
                        "totals, and PO reference from the provided document data."
                    ),
                    user_message=f"Extract structured data from document ID {document_id}",
                    tools=[{
                        "name": "extract_invoice_fields",
                        "description": "Extract structured fields from an invoice",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "vendor_name": {"type": "string"},
                                "invoice_number": {"type": "string"},
                                "invoice_date": {"type": "string"},
                                "po_reference": {"type": "string"},
                                "total_amount": {"type": "number"},
                                "currency": {"type": "string"},
                                "line_items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "description": {"type": "string"},
                                            "quantity": {"type": "number"},
                                            "unit_price": {"type": "number"},
                                            "amount": {"type": "number"},
                                        },
                                    },
                                },
                            },
                            "required": ["vendor_name", "total_amount"],
                        },
                    }],
                    state=state,
                )
                extracted = result.get("tool_input", result)
            except Exception as exc:
                return {"error": f"Document extraction failed: {exc}", "extracted_data": {}}

        return {"extracted_data": extracted}

    def _match_purchase_order(self, state: P2PState) -> dict:
        extracted = state.get("extracted_data", {})
        po_ref = extracted.get("po_reference", "")
        vendor_name = extracted.get("vendor_name", "")

        matched_po = None
        confidence = 0.0

        if po_ref:
            pos = self.search_records(
                "purchase.order",
                [("name", "=", po_ref), ("state", "in", ["purchase", "done"])],
                fields=["name", "partner_id", "amount_total", "order_line", "state"],
                limit=1,
            )
            if pos:
                matched_po = pos[0]
                confidence = 0.95

        if not matched_po and vendor_name:
            vendors = self.search_records(
                "res.partner",
                [("name", "ilike", vendor_name), ("supplier_rank", ">", 0)],
                fields=["id", "name"],
                limit=5,
            )
            if vendors:
                vendor_ids = [v["id"] for v in vendors]
                total = extracted.get("total_amount", 0)
                pos = self.search_records(
                    "purchase.order",
                    [
                        ("partner_id", "in", vendor_ids),
                        ("state", "in", ["purchase", "done"]),
                        ("amount_total", ">=", total * 0.98),
                        ("amount_total", "<=", total * 1.02),
                    ],
                    fields=["name", "partner_id", "amount_total", "order_line", "state"],
                    limit=5,
                )
                if pos:
                    matched_po = pos[0]
                    confidence = 0.75

        vendor_id = None
        if matched_po:
            partner = matched_po.get("partner_id")
            vendor_id = partner[0] if isinstance(partner, (list, tuple)) else partner

        return {
            "matched_po": matched_po,
            "po_match_confidence": confidence,
            "vendor_id": vendor_id,
        }

    def _validate_amounts(self, state: P2PState) -> dict:
        extracted = state.get("extracted_data", {})
        po = state.get("matched_po", {})
        discrepancies = []

        if not po:
            return {"discrepancies": [{"field": "po", "reason": "No PO to validate against"}]}

        inv_total = extracted.get("total_amount", 0)
        po_total = po.get("amount_total", 0)
        if po_total and abs(inv_total - po_total) / po_total > 0.02:
            discrepancies.append({
                "field": "total_amount",
                "invoice_value": inv_total,
                "po_value": po_total,
                "difference_pct": round(abs(inv_total - po_total) / po_total * 100, 2),
            })

        return {"discrepancies": discrepancies}

    def _check_goods_receipt(self, state: P2PState) -> dict:
        po = state.get("matched_po", {})
        if not po:
            return {"goods_received": False}

        po_name = po.get("name", "")
        pickings = self.search_records(
            "stock.picking",
            [("origin", "=", po_name), ("state", "=", "done")],
            fields=["id", "state"],
            limit=1,
        )
        return {"goods_received": bool(pickings)}

    def _create_draft_bill(self, state: P2PState) -> dict:
        extracted = state.get("extracted_data", {})
        po = state.get("matched_po", {})
        vendor_id = state.get("vendor_id")

        if not vendor_id:
            return {"error": "Cannot create bill without vendor", "bill_id": None}

        try:
            bill_vals = {
                "move_type": "in_invoice",
                "partner_id": vendor_id,
                "ref": extracted.get("invoice_number", ""),
            }
            bill_id = self.create_record("account.move", bill_vals)
            return {"bill_id": bill_id}
        except Exception as exc:
            return {"error": f"Bill creation failed: {exc}", "bill_id": None}

    def _route_for_approval(self, state: P2PState) -> dict:
        confidence = state.get("po_match_confidence", 0)
        discrepancies = state.get("discrepancies", [])

        if discrepancies:
            confidence *= 0.7

        overall = confidence
        if self.should_auto_execute(overall):
            decision = "auto_approve"
        elif self.needs_approval(overall):
            decision = "needs_approval"
        else:
            decision = "escalate"

        return {"approval_decision": decision, "overall_confidence": overall}

    def _suspend_for_approval(self, state: P2PState) -> dict:
        return {
            "needs_suspension": True,
            "suspension_reason": "awaiting_bill_approval",
        }

    def _post_bill(self, state: P2PState) -> dict:
        bill_id = state.get("bill_id")
        if not bill_id:
            return {"error": "No bill to post"}

        try:
            self.update_record("account.move", bill_id, {"state": "posted"})
            return {}
        except Exception as exc:
            return {"error": f"Bill posting failed: {exc}"}

    def _update_vendor_score(self, state: P2PState) -> dict:
        vendor_id = state.get("vendor_id")
        if not vendor_id:
            return {"vendor_score_delta": 0.0}

        discrepancies = state.get("discrepancies", [])
        delta = 5.0 if not discrepancies else -2.0
        return {"vendor_score_delta": delta}

    def _notify_stakeholders(self, state: P2PState) -> dict:
        notifications = []
        error = state.get("error")
        bill_id = state.get("bill_id")

        if error:
            self.notify(
                "slack", "", "P2P Agent Alert",
                f"Issue in procure-to-pay workflow: {error}",
            )
            notifications.append("error_alert")
        elif bill_id:
            self.notify(
                "slack", "", "P2P Agent Complete",
                f"Bill {bill_id} processed successfully (confidence: {state.get('overall_confidence', 0):.0%})",
            )
            notifications.append("completion")

        return {"notifications_sent": notifications}

    # ------------------------------------------------------------------
    # Routing functions
    # ------------------------------------------------------------------

    def _route_after_extraction(self, state: P2PState) -> str:
        if state.get("error") or not state.get("extracted_data"):
            return "failure"
        return "success"

    def _route_after_po_match(self, state: P2PState) -> str:
        return "found" if state.get("matched_po") else "not_found"

    def _route_after_validation(self, state: P2PState) -> str:
        return "discrepancy" if state.get("discrepancies") else "match"

    def _route_after_receipt_check(self, state: P2PState) -> str:
        return "received" if state.get("goods_received") else "not_received"

    def _route_approval_decision(self, state: P2PState) -> str:
        return state.get("approval_decision", "escalate")


register_agent(ProcureToPayAgent)
